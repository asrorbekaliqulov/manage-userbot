"""Inject sidebar navigation + pending-request badges into every template."""
from __future__ import annotations


def navigation(request):
    nav = [
        {"label": "Dashboard", "url": "dashboard:home", "icon": "grid"},
        {"label": "Accounts", "url": "dashboard:accounts", "icon": "users"},
        {"label": "Messages", "url": "dashboard:messages", "icon": "message"},
        {"label": "Schedules", "url": "dashboard:schedules", "icon": "clock"},
        {"label": "Auto-reply", "url": "dashboard:autoreplies", "icon": "reply"},
        {"label": "Scraping", "url": "dashboard:scrape_sources", "icon": "rss"},
        {"label": "Channels", "url": "dashboard:create_channel", "icon": "hash"},
        {"label": "Developers", "url": "dashboard:developers", "icon": "code"},
        {"label": "Key requests", "url": "dashboard:key_requests", "icon": "key"},
        {"label": "Logs", "url": "dashboard:logs", "icon": "list"},
        {"label": "API docs", "url": "dashboard:api_docs", "icon": "book"},
    ]

    pending_requests = 0
    if request.user.is_authenticated:
        try:
            from apps.developers.models import APIKeyRequest

            pending_requests = APIKeyRequest.objects.filter(
                status=APIKeyRequest.Status.PENDING
            ).count()
        except Exception:  # noqa: BLE001
            pending_requests = 0

    return {"nav_items": nav, "pending_requests": pending_requests}
