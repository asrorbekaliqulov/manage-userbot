"""
Low-level Telethon helpers.

The web process talks to Telegram only for short, request-scoped operations
(connecting, sending a message, fetching history). Each such operation spins up
a fresh client from a ``StringSession`` and tears it down afterwards. The
long-lived, event-driven connections (receiving messages, auto-reply) live in
the dedicated worker process (see ``apps.accounts.management.commands.run_userbots``).
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, TypeVar

from django.conf import settings
from telethon import TelegramClient
from telethon.sessions import StringSession

T = TypeVar("T")


def run_async(coro: Awaitable[T]) -> T:
    """Run an async coroutine from synchronous Django code.

    Always uses a fresh event loop so it is safe to call repeatedly from
    request handlers and Celery tasks.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()


def build_client(
    session_string: str = "",
    api_id: int | None = None,
    api_hash: str | None = None,
) -> TelegramClient:
    """Create a Telethon client backed by an in-memory StringSession."""
    return TelegramClient(
        StringSession(session_string or None),
        api_id or settings.TELEGRAM_API_ID,
        api_hash or settings.TELEGRAM_API_HASH,
        device_model="Userbot Panel",
        system_version="1.0",
        app_version="1.0",
    )


async def with_client(
    session_string: str,
    func: Callable[[TelegramClient], Awaitable[T]],
    api_id: int | None = None,
    api_hash: str | None = None,
) -> T:
    """Connect a client, run ``func`` with it, then disconnect."""
    client = build_client(session_string, api_id, api_hash)
    await client.connect()
    try:
        return await func(client)
    finally:
        await client.disconnect()
