"""
Synchronous ORM logic invoked by the (async) userbot worker.

The worker extracts plain dicts from Telethon objects in the event loop, then
calls these functions through ``asgiref.sync.sync_to_async`` so all database
access stays on a worker thread.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from apps.accounts.models import TelegramAccount
from apps.logs.services import log_action

from .models import AutoReplyRule, AutoReplyState, Message


def _content_key_for(account: TelegramAccount) -> str | None:
    if account.is_private and account.owner:
        return account.owner.get_content_key()
    return None


def save_observed_message(account_id: int, payload: dict) -> int | None:
    """Persist an observed message. Returns the new Message id (or None)."""
    try:
        account = TelegramAccount.objects.select_related("owner").get(pk=account_id)
    except TelegramAccount.DoesNotExist:
        return None

    date = payload.get("date")
    if isinstance(date, str):
        date = datetime.fromisoformat(date)
    if date is None:
        date = timezone.now()

    msg = Message(
        account=account,
        tg_message_id=payload["tg_message_id"],
        direction=payload.get("direction", Message.Direction.IN),
        kind=payload.get("kind", Message.Kind.TEXT),
        chat_id=payload["chat_id"],
        chat_title=payload.get("chat_title", "")[:255],
        chat_type=payload.get("chat_type", ""),
        sender_id=payload.get("sender_id"),
        sender_name=payload.get("sender_name", "")[:255],
        is_private=account.is_private,
        has_media=payload.get("has_media", False),
        media_type=payload.get("media_type", ""),
        date=date,
        metadata=payload.get("metadata", {}),
    )
    msg.set_content(payload.get("text", ""), _content_key_for(account))
    msg.save()

    log_action(
        category="message",
        action="message_received" if msg.direction == "in" else "message_sent",
        account=account,
        developer=account.owner,
        source="worker",
        metadata={
            "chat_id": msg.chat_id,
            "chat_title": msg.chat_title,
            "message_id": msg.tg_message_id,
            "kind": msg.kind,
            # Never log raw content for private accounts.
            "preview": "" if account.is_private else (payload.get("text", "")[:120]),
        },
    )
    return msg.pk


def compute_auto_reply(account_id: int, payload: dict) -> str | None:
    """Return the reply text an auto-reply rule wants to send, or ``None``.

    Honours mode (always/online/busy), keyword triggers, private-chat scoping
    and per-chat cooldown.
    """
    if payload.get("out"):
        return None  # never auto-reply to our own outgoing messages

    try:
        account = TelegramAccount.objects.get(pk=account_id)
    except TelegramAccount.DoesNotExist:
        return None

    chat_type = payload.get("chat_type", "")
    chat_id = payload["chat_id"]
    text = (payload.get("text") or "").lower()

    rules = AutoReplyRule.objects.filter(is_active=True).filter(
        models_q_account(account)
    )

    for rule in rules:
        if rule.only_private_chats and chat_type != "user":
            continue
        if not _mode_matches(rule.mode, account.presence):
            continue
        if rule.keywords and not any(k.lower() in text for k in rule.keywords):
            continue
        if _in_cooldown(rule, account, chat_id):
            continue

        _mark_replied(rule, account, chat_id)
        log_action(
            category="autoreply",
            action="auto_reply_fired",
            account=account,
            developer=account.owner,
            source="worker",
            metadata={"rule": rule.name, "chat_id": chat_id},
        )
        return rule.reply_text
    return None


def models_q_account(account: TelegramAccount):
    from django.db.models import Q

    return Q(apply_to_all=True) | Q(account=account)


def _mode_matches(mode: str, presence: str) -> bool:
    if mode == AutoReplyRule.Mode.ALWAYS:
        return True
    if mode == AutoReplyRule.Mode.ONLINE:
        return presence == TelegramAccount.Presence.AVAILABLE
    if mode == AutoReplyRule.Mode.BUSY:
        return presence == TelegramAccount.Presence.BUSY
    return False


def _in_cooldown(rule: AutoReplyRule, account: TelegramAccount, chat_id: int) -> bool:
    if rule.cooldown_minutes <= 0:
        return False
    state = AutoReplyState.objects.filter(
        rule=rule, account=account, chat_id=chat_id
    ).first()
    if not state:
        return False
    return state.last_reply_at > timezone.now() - timedelta(minutes=rule.cooldown_minutes)


def _mark_replied(rule: AutoReplyRule, account: TelegramAccount, chat_id: int) -> None:
    AutoReplyState.objects.update_or_create(
        rule=rule,
        account=account,
        chat_id=chat_id,
        defaults={"last_reply_at": timezone.now()},
    )
