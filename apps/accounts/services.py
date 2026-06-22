"""High level account operations used by views, tasks and the API."""
from __future__ import annotations

from django.utils import timezone

from apps.logs.services import log_action

from .models import TelegramAccount
from .telegram import auth


def finalize_login(account: TelegramAccount, result: auth.LoginResult, *, actor=None,
                   source: str = "panel", ip_address=None) -> TelegramAccount:
    """Persist a successful login result onto the account."""
    account.set_session(result.session_string)
    if result.user:
        account.telegram_user_id = result.user["telegram_user_id"]
        account.username = result.user["username"]
        account.first_name = result.user["first_name"]
        account.last_name = result.user["last_name"]
    account.status = TelegramAccount.Status.ACTIVE
    account.last_connected_at = timezone.now()
    account.save()

    log_action(
        category="auth",
        action="account_connected",
        description=f"Account {account.label} connected",
        account=account,
        developer=account.owner,
        actor=actor,
        source=source,
        ip_address=ip_address,
        metadata={"username": account.username, "user_id": account.telegram_user_id},
    )
    return account


def refresh_identity(account: TelegramAccount) -> auth.LoginResult:
    """Validate the stored session and update cached identity / status."""
    result = auth.validate_session(
        account.get_session(), account.effective_api_id, account.effective_api_hash
    )
    if result.status == "ok":
        account.status = TelegramAccount.Status.ACTIVE
        if result.user:
            account.telegram_user_id = result.user["telegram_user_id"]
            account.username = result.user["username"]
            account.first_name = result.user["first_name"]
            account.last_name = result.user["last_name"]
        if result.session_string:
            account.set_session(result.session_string)
        account.last_connected_at = timezone.now()
    else:
        account.status = TelegramAccount.Status.DISCONNECTED
    account.save()
    return result


def disconnect(account: TelegramAccount, *, actor=None, source: str = "panel") -> None:
    account.status = TelegramAccount.Status.DISCONNECTED
    account.is_enabled = False
    account.save(update_fields=["status", "is_enabled", "updated_at"])
    log_action(
        category="account",
        action="account_disconnected",
        account=account,
        developer=account.owner,
        actor=actor,
        source=source,
    )
