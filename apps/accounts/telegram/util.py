"""Shared helpers for interpreting Telethon message objects."""
from __future__ import annotations

from telethon.tl import types


def detect_kind(message) -> tuple[str, str, bool]:
    """Return ``(kind, media_type, has_media)`` for a Telethon message.

    ``kind`` matches ``apps.messaging.models.Message.Kind`` values.
    """
    if message is None:
        return ("other", "", False)

    media = getattr(message, "media", None)
    if media is None:
        if getattr(message, "action", None) is not None:
            return ("service", "", False)
        return ("text", "", False)

    # Photo
    if isinstance(media, types.MessageMediaPhoto):
        return ("photo", "photo", True)

    if isinstance(media, types.MessageMediaGeo) or isinstance(
        media, types.MessageMediaGeoLive
    ):
        return ("geo", "geo", True)
    if isinstance(media, types.MessageMediaContact):
        return ("contact", "contact", True)
    if isinstance(media, types.MessageMediaPoll):
        return ("poll", "poll", True)

    if isinstance(media, types.MessageMediaDocument):
        doc = getattr(media, "document", None)
        attrs = getattr(doc, "attributes", []) if doc else []
        is_voice = False
        is_round = False
        is_audio = False
        is_animated = False
        is_sticker = False
        filename = ""
        for a in attrs:
            if isinstance(a, types.DocumentAttributeAudio):
                is_audio = True
                is_voice = bool(getattr(a, "voice", False))
            elif isinstance(a, types.DocumentAttributeVideo):
                is_round = bool(getattr(a, "round_message", False))
            elif isinstance(a, types.DocumentAttributeAnimated):
                is_animated = True
            elif isinstance(a, types.DocumentAttributeSticker):
                is_sticker = True
            elif isinstance(a, types.DocumentAttributeFilename):
                filename = a.file_name or ""
        mime = getattr(doc, "mime_type", "") if doc else ""
        if is_sticker:
            return ("sticker", "sticker", True)
        if is_animated or mime == "video/mp4" and not filename:
            return ("gif", "gif", True)
        if is_voice:
            return ("voice", "voice", True)
        if is_audio:
            return ("audio", "audio", True)
        if mime.startswith("video"):
            return ("video", "video", True)
        return ("document", mime or "document", True)

    return ("other", "media", True)
