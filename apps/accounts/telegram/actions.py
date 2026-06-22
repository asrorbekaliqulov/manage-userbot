"""
Request-scoped Telegram actions performed on behalf of a connected account:
sending messages, creating channels/groups, resolving entities and reading
history. Every public function returns plain dicts so callers (views, tasks,
API) do not need to know about Telethon internals.
"""
from __future__ import annotations

from telethon import functions
from telethon.tl.types import Channel, Chat, User

from .client import run_async, with_client


def _entity_summary(entity) -> dict:
    if isinstance(entity, User):
        return {
            "id": entity.id,
            "type": "user",
            "title": f"{entity.first_name or ''} {entity.last_name or ''}".strip(),
            "username": entity.username or "",
        }
    if isinstance(entity, (Channel, Chat)):
        return {
            "id": entity.id,
            "type": "channel" if isinstance(entity, Channel) else "chat",
            "title": getattr(entity, "title", ""),
            "username": getattr(entity, "username", "") or "",
        }
    return {"id": getattr(entity, "id", None), "type": "unknown", "title": "", "username": ""}


def send_message(
    session_string: str,
    api_id: int,
    api_hash: str,
    target: str,
    text: str,
    *,
    file_path: str | None = None,
    reply_to: int | None = None,
    silent: bool = False,
    parse_mode: str | None = None,
) -> dict:
    """Send a message (optionally with a file) to ``target``.

    ``target`` may be a username, phone, t.me link, or numeric id.
    ``parse_mode`` may be ``"html"`` or ``"md"`` for rich formatting (bold,
    italic, underline, strikethrough, code, links) just like Telegram.
    """

    async def _do(client):
        entity = await client.get_entity(_coerce_target(target))
        msg = await client.send_message(
            entity,
            text,
            file=file_path,
            reply_to=reply_to,
            silent=silent,
            parse_mode=parse_mode,
        )
        return {
            "ok": True,
            "message_id": msg.id,
            "date": msg.date.isoformat() if msg.date else None,
            "to": _entity_summary(entity),
        }

    try:
        return run_async(with_client(session_string, _do, api_id, api_hash))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def create_channel(
    session_string: str,
    api_id: int,
    api_hash: str,
    title: str,
    about: str = "",
    *,
    megagroup: bool = False,
) -> dict:
    """Create a broadcast channel (or a supergroup when ``megagroup=True``)."""

    async def _do(client):
        result = await client(
            functions.channels.CreateChannelRequest(
                title=title, about=about, megagroup=megagroup, broadcast=not megagroup
            )
        )
        channel = result.chats[0]
        return {"ok": True, "channel": _entity_summary(channel)}

    try:
        return run_async(with_client(session_string, _do, api_id, api_hash))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def create_group(
    session_string: str,
    api_id: int,
    api_hash: str,
    title: str,
    members: list[str] | None = None,
) -> dict:
    """Create a basic group with optional initial members."""

    async def _do(client):
        users = []
        for m in members or []:
            try:
                users.append(await client.get_entity(_coerce_target(m)))
            except Exception:  # noqa: BLE001
                continue
        result = await client(
            functions.messages.CreateChatRequest(users=users or ["me"], title=title)
        )
        chats = getattr(result, "chats", None) or result.updates.chats  # type: ignore[attr-defined]
        return {"ok": True, "group": _entity_summary(chats[0])}

    try:
        return run_async(with_client(session_string, _do, api_id, api_hash))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def fetch_dialogs(session_string: str, api_id: int, api_hash: str, limit: int = 100) -> dict:
    """List the most recent conversations for the account."""

    async def _do(client):
        dialogs = []
        async for d in client.iter_dialogs(limit=limit):
            dialogs.append(
                {
                    **_entity_summary(d.entity),
                    "unread": d.unread_count,
                    "last_message": (d.message.message if d.message else "") or "",
                    "date": d.date.isoformat() if d.date else None,
                }
            )
        return {"ok": True, "dialogs": dialogs}

    try:
        return run_async(with_client(session_string, _do, api_id, api_hash))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def fetch_history(
    session_string: str,
    api_id: int,
    api_hash: str,
    target: str,
    limit: int = 50,
) -> dict:
    """Fetch recent messages from a conversation."""

    async def _do(client):
        entity = await client.get_entity(_coerce_target(target))
        messages = []
        async for m in client.iter_messages(entity, limit=limit):
            messages.append(
                {
                    "id": m.id,
                    "out": m.out,
                    "text": m.message or "",
                    "date": m.date.isoformat() if m.date else None,
                    "sender_id": m.sender_id,
                    "media": bool(m.media),
                }
            )
        return {"ok": True, "messages": messages, "chat": _entity_summary(entity)}

    try:
        return run_async(with_client(session_string, _do, api_id, api_hash))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def _coerce_target(target: str):
    """Turn a numeric-looking string into an int id, otherwise keep the string."""
    s = str(target).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return s



def fetch_messages_since(
    session_string: str,
    api_id: int,
    api_hash: str,
    target: str,
    min_id: int = 0,
    limit: int = 50,
) -> dict:
    """Fetch messages newer than ``min_id`` from ``target`` (oldest first)."""
    from .util import detect_kind

    async def _do(client):
        entity = await client.get_entity(_coerce_target(target))
        messages = []
        async for m in client.iter_messages(entity, limit=limit, min_id=min_id):
            kind, media_type, has_media = detect_kind(m)
            messages.append(
                {
                    "tg_message_id": m.id,
                    "text": m.message or "",
                    "kind": kind,
                    "media_type": media_type,
                    "has_media": has_media,
                    "date": m.date.isoformat() if m.date else None,
                }
            )
        messages.reverse()  # chronological order
        return {"ok": True, "messages": messages, "chat": _entity_summary(entity)}

    try:
        return run_async(with_client(session_string, _do, api_id, api_hash))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def forward_messages(
    session_string: str,
    api_id: int,
    api_hash: str,
    from_chat: str,
    message_ids: list[int],
    targets: list[str],
) -> dict:
    """Forward messages from ``from_chat`` to each target."""

    async def _do(client):
        source = await client.get_entity(_coerce_target(from_chat))
        results = []
        for target in targets:
            try:
                dest = await client.get_entity(_coerce_target(target))
                await client.forward_messages(dest, message_ids, source)
                results.append({"target": target, "ok": True})
            except Exception as exc:  # noqa: BLE001
                results.append({"target": target, "ok": False, "error": str(exc)})
        return {"ok": True, "results": results}

    try:
        return run_async(with_client(session_string, _do, api_id, api_hash))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}



def fetch_chat(
    session_string: str,
    api_id: int,
    api_hash: str,
    target: str,
    limit: int = 50,
) -> dict:
    """Fetch a conversation for the chat UI, with Telegram HTML formatting.

    Each message includes the rich-formatted ``html`` (bold/italic/links/emoji
    preserved), ``out`` flag, sender name, date and media info.
    """
    from .util import detect_kind

    async def _do(client):
        # Make ``message.text`` return Telegram HTML (entities -> tags).
        client.parse_mode = "html"
        entity = await client.get_entity(_coerce_target(target))
        messages = []
        async for m in client.iter_messages(entity, limit=limit):
            kind, media_type, has_media = detect_kind(m)
            sender_name = ""
            try:
                sender = await m.get_sender()
                if sender is not None:
                    sender_name = getattr(sender, "title", "") or (
                        f"{getattr(sender, 'first_name', '')} "
                        f"{getattr(sender, 'last_name', '')}".strip()
                    )
            except Exception:  # noqa: BLE001
                pass
            messages.append(
                {
                    "id": m.id,
                    "out": bool(m.out),
                    "html": m.text or "",
                    "raw": m.raw_text or "",
                    "sender_name": sender_name,
                    "date": m.date.isoformat() if m.date else None,
                    "kind": kind,
                    "media_type": media_type,
                    "has_media": has_media,
                }
            )
        messages.reverse()  # chronological (oldest first)
        return {"ok": True, "messages": messages, "chat": _entity_summary(entity)}

    try:
        return run_async(with_client(session_string, _do, api_id, api_hash))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
