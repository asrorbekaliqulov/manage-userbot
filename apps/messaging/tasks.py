"""Celery tasks for scheduled message delivery."""
from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.accounts.models import TelegramAccount
from apps.accounts.telegram.actions import send_message
from apps.logs.services import log_action

from .models import ScheduledMessage


@shared_task
def dispatch_due_schedules() -> int:
    """Find schedules whose time has come and dispatch them.

    Intended to run every minute via Celery beat.
    """
    now = timezone.now()
    due = ScheduledMessage.objects.filter(
        status=ScheduledMessage.Status.PENDING, scheduled_for__lte=now
    )
    count = 0
    for schedule in due:
        send_scheduled_message.delay(schedule.pk)
        count += 1
    return count


@shared_task
def send_scheduled_message(schedule_id: int) -> dict:
    try:
        schedule = ScheduledMessage.objects.get(pk=schedule_id)
    except ScheduledMessage.DoesNotExist:
        return {"ok": False, "error": "not found"}

    if schedule.status not in (
        ScheduledMessage.Status.PENDING,
        ScheduledMessage.Status.PARTIAL,
    ):
        return {"ok": False, "error": f"status={schedule.status}"}

    accounts = _resolve_accounts(schedule)
    results = []
    sent_ok = 0
    total = 0

    for account in accounts:
        session = account.get_session()
        for target in schedule.targets:
            total += 1
            res = send_message(
                session,
                account.effective_api_id,
                account.effective_api_hash,
                str(target),
                schedule.text,
                file_path=schedule.file_path or None,
                silent=schedule.silent,
            )
            ok = bool(res.get("ok"))
            sent_ok += int(ok)
            results.append(
                {
                    "account": account.label,
                    "target": target,
                    "ok": ok,
                    "error": res.get("error", ""),
                    "message_id": res.get("message_id"),
                }
            )
            log_action(
                category="schedule",
                action="scheduled_message_sent" if ok else "scheduled_message_failed",
                account=account,
                developer=schedule.owner,
                source="worker",
                metadata={"target": target, "schedule_id": schedule.pk, "ok": ok},
            )

    if sent_ok == total and total > 0:
        schedule.status = ScheduledMessage.Status.SENT
    elif sent_ok == 0:
        schedule.status = ScheduledMessage.Status.FAILED
    else:
        schedule.status = ScheduledMessage.Status.PARTIAL
    schedule.result_log = results
    schedule.sent_at = timezone.now()
    schedule.save(update_fields=["status", "result_log", "sent_at", "updated_at"])

    return {"ok": sent_ok > 0, "sent": sent_ok, "total": total}


def _resolve_accounts(schedule: ScheduledMessage):
    if schedule.from_mode == ScheduledMessage.FromMode.ALL:
        qs = TelegramAccount.objects.filter(
            is_enabled=True, status=TelegramAccount.Status.ACTIVE
        ).exclude(session_enc="")
        if schedule.owner_id:
            qs = qs.filter(owner_id=schedule.owner_id)
        return list(qs)
    if schedule.account and schedule.account.session_enc:
        return [schedule.account]
    return []
