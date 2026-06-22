from __future__ import annotations

from django.db import models


class ScrapeSource(models.Model):
    """A channel/group to monitor; matching posts are saved and optionally
    forwarded to one or more destinations."""

    name = models.CharField(max_length=150)
    # Source channel: @username, t.me link or numeric id. The reading account
    # must be a member / subscriber of it.
    source = models.CharField(max_length=255)

    # Account used to read the source.
    account = models.ForeignKey(
        "accounts.TelegramAccount",
        on_delete=models.CASCADE,
        related_name="scrape_sources",
    )

    # Keyword filters (case-insensitive). Empty list => capture everything.
    keywords = models.JSONField(default=list, blank=True)
    # Match mode: "any" (default) or "all".
    match_mode = models.CharField(max_length=4, default="any")

    # Auto-forward matched posts to these targets.
    forward_targets = models.JSONField(default=list, blank=True)
    auto_forward = models.BooleanField(default=False)
    forward_account = models.ForeignKey(
        "accounts.TelegramAccount",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="forward_sources",
        help_text="Account used to forward. Defaults to the reading account.",
    )
    extra_caption = models.TextField(blank=True)

    last_message_id = models.BigIntegerField(default=0)
    poll_interval_minutes = models.PositiveIntegerField(default=5)

    is_active = models.BooleanField(default=True)
    owner = models.ForeignKey(
        "developers.Developer", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="scrape_sources",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.source})"


class ScrapedPost(models.Model):
    """A post captured from a scrape source."""

    source = models.ForeignKey(
        ScrapeSource, on_delete=models.CASCADE, related_name="posts"
    )
    tg_message_id = models.BigIntegerField()
    text = models.TextField(blank=True)
    matched_keywords = models.JSONField(default=list, blank=True)
    has_media = models.BooleanField(default=False)
    media_type = models.CharField(max_length=32, blank=True)
    post_date = models.DateTimeField(null=True, blank=True)

    forwarded = models.BooleanField(default=False)
    forwarded_at = models.DateTimeField(null=True, blank=True)
    forward_log = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-post_date", "-created_at"]
        unique_together = ("source", "tg_message_id")
        indexes = [models.Index(fields=["source", "post_date"])]

    def __str__(self):
        return f"Post {self.tg_message_id} from {self.source_id}"
