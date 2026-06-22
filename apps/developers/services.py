"""Approve / reject API-key requests and issue keys."""
from __future__ import annotations

from django.utils import timezone

from apps.logs.services import log_action

from .models import APIKey, APIKeyRequest, Developer
from .notifications import notify_developer

KEY_MESSAGE = (
    "Hello {name},\n\n"
    "Your API key request for the Userbot Panel has been approved.\n\n"
    "API key (store it securely, it is shown only once):\n"
    "{raw_key}\n\n"
    "Use it in the Authorization header:\n"
    "    Authorization: Api-Key {raw_key}\n\n"
    "Granted scopes: {scopes}\n\n"
    "Docs: see the developer documentation page in the panel.\n"
)


def approve_request(req: APIKeyRequest, reviewer=None) -> tuple[APIKey, str]:
    """Approve a request: ensure a Developer exists, issue a key and notify."""
    developer = req.developer
    if developer is None:
        developer = Developer.objects.create(
            name=req.name,
            organization=req.organization,
            email=req.email,
            telegram_username=req.telegram_username,
        )
        req.developer = developer

    scopes = req.requested_scopes or None
    key, raw_key = APIKey.generate(
        developer, label=f"key for {req.name}", scopes=scopes, request=req
    )

    req.status = APIKeyRequest.Status.APPROVED
    req.reviewed_by = reviewer if getattr(reviewer, "is_authenticated", False) else None
    req.reviewed_at = timezone.now()
    req.save()

    body = KEY_MESSAGE.format(
        name=developer.name,
        raw_key=raw_key,
        scopes=", ".join(key.scopes or []),
    )
    delivery = notify_developer(
        developer,
        "Your Userbot Panel API key",
        body,
        method=req.delivery_method,
    )

    log_action(
        category="developer",
        action="api_key_issued",
        description=f"API key issued to {developer.name}",
        developer=developer,
        actor=reviewer,
        source="panel",
        metadata={"key_prefix": key.prefix, "delivery": delivery, "scopes": key.scopes},
    )
    return key, raw_key


def reject_request(req: APIKeyRequest, reviewer=None, note: str = "") -> APIKeyRequest:
    req.status = APIKeyRequest.Status.REJECTED
    req.review_note = note
    req.reviewed_by = reviewer if getattr(reviewer, "is_authenticated", False) else None
    req.reviewed_at = timezone.now()
    req.save()

    if req.developer or req.email or req.telegram_username:
        target_dev = req.developer or Developer(
            name=req.name, email=req.email, telegram_username=req.telegram_username
        )
        notify_developer(
            target_dev,
            "Your Userbot Panel API key request",
            f"Hello {req.name},\n\nUnfortunately your API key request was not "
            f"approved.\n\nReason: {note or 'not specified'}",
            method=req.delivery_method,
        )

    log_action(
        category="developer",
        action="api_key_request_rejected",
        developer=req.developer,
        actor=reviewer,
        source="panel",
        metadata={"note": note},
    )
    return req
