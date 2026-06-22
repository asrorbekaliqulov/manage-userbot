"""Celery tasks for account maintenance."""
from __future__ import annotations

from celery import shared_task

from .models import TelegramAccount
from .services import refresh_identity


@shared_task
def refresh_account_identity(account_id: int) -> str:
    try:
        account = TelegramAccount.objects.get(pk=account_id)
    except TelegramAccount.DoesNotExist:
        return "missing"
    result = refresh_identity(account)
    return result.status


@shared_task
def refresh_all_accounts() -> int:
    count = 0
    for account in TelegramAccount.objects.exclude(session_enc=""):
        refresh_identity(account)
        count += 1
    return count
