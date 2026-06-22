from django.conf import settings
from django.db import models


class ActionLog(models.Model):
    """
    Immutable audit trail.

    Every meaningful action taken on or by an account is recorded here: logins,
    edits, messages sent, channels created, scrapes, auto-replies fired, API
    calls, etc. For developer-owned accounts this is the *only* visibility the
    admin has by default - the contents of conversations stay private, but the
    fact that an action happened is always logged.
    """

    class Category(models.TextChoices):
        ACCOUNT = "account", "Account"
        AUTH = "auth", "Authentication"
        MESSAGE = "message", "Message"
        SCHEDULE = "schedule", "Schedule"
        SCRAPE = "scrape", "Scrape"
        AUTOREPLY = "autoreply", "Auto-reply"
        CHANNEL = "channel", "Channel/Group"
        API = "api", "API"
        DEVELOPER = "developer", "Developer"
        SYSTEM = "system", "System"

    category = models.CharField(max_length=16, choices=Category.choices, db_index=True)
    action = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    account = models.ForeignKey(
        "accounts.TelegramAccount",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logs",
    )
    developer = models.ForeignKey(
        "developers.Developer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="action_logs",
    )

    # "panel" (admin user), "api" (developer key) or "worker" (background).
    source = models.CharField(max_length=16, default="system")

    # Structured payload (target, message_id, changed fields, etc.).
    metadata = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "created_at"]),
            models.Index(fields=["account", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.category}] {self.action} @ {self.created_at:%Y-%m-%d %H:%M}"
