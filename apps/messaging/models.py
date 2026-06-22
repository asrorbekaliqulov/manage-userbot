from __future__ import annotations

from django.db import models

from apps.common.crypto import decrypt_secret, encrypt_secret


class Message(models.Model):
    """A message observed (received or sent) by a connected account.

    For *private* (developer-owned) accounts the textual content is stored
    encrypted with the developer's content key and ``text`` is left blank, so
    the admin panel cannot read it without the developer's API key.
    """

    class Direction(models.TextChoices):
        IN = "in", "Incoming"
        OUT = "out", "Outgoing"

    class Kind(models.TextChoices):
        TEXT = "text", "Text"
        PHOTO = "photo", "Photo"
        VIDEO = "video", "Video"
        VOICE = "voice", "Voice"
        AUDIO = "audio", "Audio"
        DOCUMENT = "document", "Document"
        STICKER = "sticker", "Sticker"
        GIF = "gif", "GIF / Animation"
        CONTACT = "contact", "Contact"
        GEO = "geo", "Location"
        POLL = "poll", "Poll"
        SERVICE = "service", "Service message"
        OTHER = "other", "Other"

    account = models.ForeignKey(
        "accounts.TelegramAccount", on_delete=models.CASCADE, related_name="messages"
    )
    tg_message_id = models.BigIntegerField()
    direction = models.CharField(max_length=4, choices=Direction.choices)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.TEXT)

    chat_id = models.BigIntegerField(db_index=True)
    chat_title = models.CharField(max_length=255, blank=True)
    chat_type = models.CharField(max_length=16, blank=True)  # user/group/channel

    sender_id = models.BigIntegerField(null=True, blank=True)
    sender_name = models.CharField(max_length=255, blank=True)

    # Content: plaintext for public accounts, encrypted for private ones.
    is_private = models.BooleanField(default=False)
    text = models.TextField(blank=True)
    text_enc = models.TextField(blank=True)

    has_media = models.BooleanField(default=False)
    media_type = models.CharField(max_length=32, blank=True)

    date = models.DateTimeField(db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]
        unique_together = ("account", "chat_id", "tg_message_id", "direction")
        indexes = [
            models.Index(fields=["account", "date"]),
            models.Index(fields=["chat_id", "date"]),
        ]

    def __str__(self):
        return f"{self.direction} msg {self.tg_message_id} in {self.chat_title or self.chat_id}"

    def set_content(self, text: str, content_key: str | None) -> None:
        """Store text, encrypting it when the account is private."""
        if self.is_private:
            self.text = ""
            self.text_enc = encrypt_secret_with(text or "", content_key)
        else:
            self.text = text or ""
            self.text_enc = ""

    def get_content(self, content_key: str | None = None) -> str | None:
        """Return the message text.

        Public messages return their text directly. Private messages require
        the developer content key; without it ``None`` is returned so the panel
        can show a "locked" placeholder.
        """
        if not self.is_private:
            return self.text
        if not content_key:
            return None
        try:
            return decrypt_secret_with(self.text_enc, content_key)
        except Exception:  # noqa: BLE001
            return None


def encrypt_secret_with(plaintext: str, content_key: str | None) -> str:
    """Encrypt content with a developer content key (Fernet key string)."""
    from cryptography.fernet import Fernet

    if not content_key:
        # Fall back to server key so data is never stored in the clear.
        return encrypt_secret(plaintext)
    return Fernet(content_key.encode()).encrypt((plaintext or "").encode()).decode()


def decrypt_secret_with(token: str, content_key: str | None) -> str:
    from cryptography.fernet import Fernet

    if not token:
        return ""
    if not content_key:
        return decrypt_secret(token)
    return Fernet(content_key.encode()).decrypt(token.encode()).decode()


class ScheduledMessage(models.Model):
    """A message (or broadcast) to be sent at a specific time.

    The same payload can be delivered from a single account or fanned out
    across all enabled accounts, to one or many targets (users / channels /
    groups).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        PARTIAL = "partial", "Partially sent"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class FromMode(models.TextChoices):
        SINGLE = "single", "Single account"
        ALL = "all", "All enabled accounts"

    title = models.CharField(max_length=150, blank=True)
    text = models.TextField(blank=True)
    file_path = models.CharField(max_length=512, blank=True)

    from_mode = models.CharField(
        max_length=8, choices=FromMode.choices, default=FromMode.SINGLE
    )
    account = models.ForeignKey(
        "accounts.TelegramAccount",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="scheduled_messages",
    )
    # List of targets: usernames / ids / t.me links / channel handles.
    targets = models.JSONField(default=list)

    scheduled_for = models.DateTimeField(db_index=True)
    silent = models.BooleanField(default=False)

    # Optional recurrence (cron-like). Empty => one-shot.
    repeat_cron = models.CharField(max_length=64, blank=True)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    result_log = models.JSONField(default=list, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    owner = models.ForeignKey(
        "developers.Developer", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="scheduled_messages",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_for"]

    def __str__(self):
        return self.title or f"Scheduled #{self.pk}"


class AutoReplyRule(models.Model):
    """Auto-reply configuration applied by the worker to incoming DMs.

    Two common modes:
      * ONLINE  - reply when the account is "online"/available.
      * BUSY    - reply with a "busy / away" message.
    Rules can target a single account or all accounts, and can be triggered by
    keywords or apply to every incoming message.
    """

    class Mode(models.TextChoices):
        ALWAYS = "always", "Always"
        ONLINE = "online", "When online"
        BUSY = "busy", "When busy / away"

    name = models.CharField(max_length=120)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.ALWAYS)

    # Empty => applies to all enabled accounts.
    account = models.ForeignKey(
        "accounts.TelegramAccount", null=True, blank=True,
        on_delete=models.CASCADE, related_name="autoreply_rules",
    )
    apply_to_all = models.BooleanField(default=False)

    # Optional keyword triggers (case-insensitive). Empty => any message.
    keywords = models.JSONField(default=list, blank=True)
    reply_text = models.TextField()

    # Only reply to private chats (DMs), not groups/channels.
    only_private_chats = models.BooleanField(default=True)
    # Avoid spamming: minimum minutes between replies to the same chat.
    cooldown_minutes = models.PositiveIntegerField(default=60)

    is_active = models.BooleanField(default=True)
    owner = models.ForeignKey(
        "developers.Developer", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="autoreply_rules",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class AutoReplyState(models.Model):
    """Tracks the last time a rule replied to a chat (for cooldown)."""

    rule = models.ForeignKey(AutoReplyRule, on_delete=models.CASCADE, related_name="states")
    account = models.ForeignKey("accounts.TelegramAccount", on_delete=models.CASCADE)
    chat_id = models.BigIntegerField()
    last_reply_at = models.DateTimeField()

    class Meta:
        unique_together = ("rule", "account", "chat_id")
