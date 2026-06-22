"""
Long-running worker that keeps all enabled accounts online.

For every enabled, connected account it opens a live Telethon connection and:
  * records incoming (and outgoing) messages into the database, and
  * fires auto-reply rules.

Run it as its own process (separate from the web server):

    python manage.py run_userbots

Scheduled messages and channel scraping are handled by Celery beat, not here.
"""
from __future__ import annotations

import asyncio
import logging

from asgiref.sync import sync_to_async
from django.core.management.base import BaseCommand

from apps.accounts.models import TelegramAccount
from apps.accounts.telegram.client import build_client
from apps.accounts.telegram.util import detect_kind
from apps.messaging.handlers import compute_auto_reply, save_observed_message

logger = logging.getLogger("userbots")


class Command(BaseCommand):
    help = "Keep all enabled accounts online to receive messages and auto-reply."

    def handle(self, *args, **options):
        try:
            asyncio.run(self._main())
        except KeyboardInterrupt:
            self.stdout.write("Shutting down userbot worker.")

    async def _main(self):
        accounts = await sync_to_async(list)(
            TelegramAccount.objects.filter(
                is_enabled=True, status=TelegramAccount.Status.ACTIVE
            ).exclude(session_enc="")
        )
        if not accounts:
            self.stdout.write("No enabled, connected accounts to run.")
            return

        clients = []
        for account in accounts:
            client = await self._start_account(account)
            if client:
                clients.append(client)

        if not clients:
            self.stdout.write("No clients could be started.")
            return

        self.stdout.write(f"Running {len(clients)} account(s). Press Ctrl+C to stop.")
        await asyncio.gather(*(c.run_until_disconnected() for c in clients))

    async def _start_account(self, account: TelegramAccount):
        from telethon import events

        session = await sync_to_async(account.get_session)()
        client = build_client(session, account.effective_api_id, account.effective_api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.warning("Account %s not authorized; skipping", account.label)
                await client.disconnect()
                return None
        except Exception:  # noqa: BLE001
            logger.exception("Failed to connect account %s", account.label)
            return None

        account_id = account.pk

        @client.on(events.NewMessage(incoming=True))
        async def _on_new_message(event):  # noqa: ANN001
            try:
                payload = await self._extract_payload(event, direction="in")
                await sync_to_async(save_observed_message)(account_id, payload)
                reply = await sync_to_async(compute_auto_reply)(account_id, payload)
                if reply:
                    await event.respond(reply)
            except Exception:  # noqa: BLE001
                logger.exception("Error handling message for account %s", account_id)

        @client.on(events.NewMessage(outgoing=True))
        async def _on_out_message(event):  # noqa: ANN001
            try:
                payload = await self._extract_payload(event, direction="out")
                await sync_to_async(save_observed_message)(account_id, payload)
            except Exception:  # noqa: BLE001
                logger.exception("Error handling outgoing message for %s", account_id)

        self.stdout.write(f"  + {account.label} online")
        return client

    async def _extract_payload(self, event, direction: str) -> dict:
        message = event.message
        kind, media_type, has_media = detect_kind(message)

        chat_type = "user"
        if event.is_group:
            chat_type = "group"
        elif event.is_channel:
            chat_type = "channel"

        chat_title = ""
        try:
            chat = await event.get_chat()
            chat_title = getattr(chat, "title", "") or (
                f"{getattr(chat, 'first_name', '')} {getattr(chat, 'last_name', '')}".strip()
            )
        except Exception:  # noqa: BLE001
            pass

        sender_name = ""
        try:
            sender = await event.get_sender()
            if sender is not None:
                sender_name = getattr(sender, "title", "") or (
                    f"{getattr(sender, 'first_name', '')} "
                    f"{getattr(sender, 'last_name', '')}".strip()
                )
        except Exception:  # noqa: BLE001
            pass

        return {
            "tg_message_id": message.id,
            "direction": direction,
            "out": bool(getattr(message, "out", direction == "out")),
            "kind": kind,
            "media_type": media_type,
            "has_media": has_media,
            "chat_id": event.chat_id,
            "chat_title": chat_title,
            "chat_type": chat_type,
            "sender_id": event.sender_id,
            "sender_name": sender_name,
            "text": message.message or "",
            "date": message.date.isoformat() if message.date else None,
            "metadata": {},
        }
