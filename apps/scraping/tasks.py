"""Celery tasks for channel scraping & forwarding."""
from __future__ import annotations

from datetime import datetime

from celery import shared_task
from django.utils import timezone

from apps.accounts.telegram.actions import fetch_messages_since, forward_messages
from apps.logs.services import log_action

from .models import ScrapedPost, ScrapeSource


def _matches(text: str, keywords: list[str], mode: str) -> list[str]:
    if not keywords:
        return []  # capture everything; no specific matches
    lowered = (text or "").lower()
    hits = [k for k in keywords if k.lower() in lowered]
    return hits


@shared_task
def scrape_all_sources() -> int:
    count = 0
    for source in ScrapeSource.objects.filter(is_active=True):
        scrape_source.delay(source.pk)
        count += 1
    return count


@shared_task
def scrape_source(source_id: int) -> dict:
    try:
        source = ScrapeSource.objects.select_related("account").get(pk=source_id)
    except ScrapeSource.DoesNotExist:
        return {"ok": False, "error": "not found"}

    account = source.account
    if not account.session_enc:
        return {"ok": False, "error": "reading account not connected"}

    fetched = fetch_messages_since(
        account.get_session(),
        account.effective_api_id,
        account.effective_api_hash,
        source.source,
        min_id=source.last_message_id,
        limit=100,
    )
    if not fetched.get("ok"):
        log_action(
            category="scrape",
            action="scrape_failed",
            account=account,
            developer=source.owner,
            source="worker",
            metadata={"source": source.source, "error": fetched.get("error")},
        )
        return fetched

    new_max = source.last_message_id
    saved = 0
    to_forward: list[int] = []

    for m in fetched["messages"]:
        new_max = max(new_max, m["tg_message_id"])
        capture_all = not source.keywords
        hits = _matches(m["text"], source.keywords, source.match_mode)
        matched = capture_all or (
            (len(hits) == len(source.keywords)) if source.match_mode == "all" else bool(hits)
        )
        if not matched:
            continue

        post_date = m.get("date")
        if isinstance(post_date, str):
            post_date = datetime.fromisoformat(post_date)

        post, created = ScrapedPost.objects.get_or_create(
            source=source,
            tg_message_id=m["tg_message_id"],
            defaults={
                "text": m["text"],
                "matched_keywords": hits,
                "has_media": m["has_media"],
                "media_type": m["media_type"],
                "post_date": post_date or timezone.now(),
            },
        )
        if created:
            saved += 1
            if source.auto_forward and source.forward_targets:
                to_forward.append(m["tg_message_id"])

    if new_max != source.last_message_id:
        source.last_message_id = new_max
        source.save(update_fields=["last_message_id", "updated_at"])

    log_action(
        category="scrape",
        action="scrape_completed",
        account=account,
        developer=source.owner,
        source="worker",
        metadata={"source": source.source, "new_posts": saved},
    )

    if to_forward:
        forward_scraped_posts.delay(source.pk, to_forward)

    return {"ok": True, "new_posts": saved}


@shared_task
def forward_scraped_posts(source_id: int, message_ids: list[int]) -> dict:
    try:
        source = ScrapeSource.objects.select_related(
            "account", "forward_account"
        ).get(pk=source_id)
    except ScrapeSource.DoesNotExist:
        return {"ok": False, "error": "not found"}

    fwd_account = source.forward_account or source.account
    if not fwd_account.session_enc:
        return {"ok": False, "error": "forward account not connected"}

    result = forward_messages(
        fwd_account.get_session(),
        fwd_account.effective_api_id,
        fwd_account.effective_api_hash,
        source.source,
        message_ids,
        source.forward_targets,
    )

    now = timezone.now()
    ScrapedPost.objects.filter(
        source=source, tg_message_id__in=message_ids
    ).update(forwarded=result.get("ok", False), forwarded_at=now, forward_log=result.get("results", []))

    log_action(
        category="scrape",
        action="scraped_posts_forwarded",
        account=fwd_account,
        developer=source.owner,
        source="worker",
        metadata={"count": len(message_ids), "targets": source.forward_targets},
    )
    return result
