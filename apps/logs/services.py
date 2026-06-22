"""Helper for writing audit-log entries from anywhere in the codebase."""
from __future__ import annotations

from .models import ActionLog


def log_action(
    *,
    category: str,
    action: str,
    description: str = "",
    account=None,
    developer=None,
    actor=None,
    source: str = "system",
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> ActionLog:
    """Create an :class:`ActionLog` entry.

    Designed to never raise in normal flow control paths - logging must not
    break the action it is recording.
    """
    return ActionLog.objects.create(
        category=category,
        action=action,
        description=description or "",
        account=account,
        developer=developer,
        actor=actor if (actor and getattr(actor, "is_authenticated", False)) else None,
        source=source,
        metadata=metadata or {},
        ip_address=ip_address,
    )
