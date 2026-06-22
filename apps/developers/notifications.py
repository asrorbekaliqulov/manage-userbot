"""Deliver issued API keys / messages to developers via email and/or Telegram."""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not to_email:
        return False
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [to_email],
            fail_silently=False,
        )
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Failed to send email to %s", to_email)
        return False


def send_telegram(target: str, body: str) -> bool:
    """Send a Telegram DM from the configured notifier account.

    ``target`` is a username or numeric user id. Returns ``True`` on success.
    """
    from apps.accounts.models import TelegramAccount
    from apps.accounts.telegram.actions import send_message

    phone = settings.NOTIFIER_ACCOUNT_PHONE
    if not (phone and target):
        return False
    account = (
        TelegramAccount.objects.filter(phone=phone, status="active")
        .exclude(session_enc="")
        .first()
    )
    if not account:
        logger.warning("No active notifier account configured (phone=%s)", phone)
        return False
    result = send_message(
        account.get_session(),
        account.effective_api_id,
        account.effective_api_hash,
        target,
        body,
    )
    return bool(result.get("ok"))


def notify_developer(developer, subject: str, body: str, *, method: str = "email") -> dict:
    """Notify a developer via the requested channel(s)."""
    outcome = {"email": None, "telegram": None}
    if method in ("email", "both"):
        outcome["email"] = send_email(developer.email, subject, body)
    if method in ("telegram", "both"):
        target = developer.telegram_username or (
            str(developer.telegram_user_id) if developer.telegram_user_id else ""
        )
        outcome["telegram"] = send_telegram(target, f"{subject}\n\n{body}")
    return outcome
