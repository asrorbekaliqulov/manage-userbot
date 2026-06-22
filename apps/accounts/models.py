from django.conf import settings
from django.db import models

from apps.common.crypto import decrypt_secret, encrypt_secret


class TelegramAccount(models.Model):
    """A Telegram *user* account (userbot) connected to the platform."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending login"
        ACTIVE = "active", "Active"
        DISCONNECTED = "disconnected", "Disconnected"
        ERROR = "error", "Error"
        BANNED = "banned", "Banned / restricted"

    label = models.CharField(max_length=120, help_text="Human friendly name")
    phone = models.CharField(max_length=32, blank=True)

    # Per-account Telegram app credentials (fall back to project defaults).
    api_id = models.IntegerField(null=True, blank=True)
    api_hash = models.CharField(max_length=64, blank=True)

    # Encrypted Telethon StringSession.
    session_enc = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    is_2fa_enabled = models.BooleanField(default=False)

    # Cached identity (filled in after a successful login).
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    username = models.CharField(max_length=64, blank=True)
    first_name = models.CharField(max_length=128, blank=True)
    last_name = models.CharField(max_length=128, blank=True)

    # Ownership / privacy.
    # When ``owner`` is a developer, the account's message content is treated as
    # private: the admin panel cannot read it without the developer's API key.
    owner = models.ForeignKey(
        "developers.Developer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="accounts",
    )
    is_private = models.BooleanField(
        default=False,
        help_text="If true, message content is encrypted with the owner's API key "
        "and is not readable from the admin panel without it.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_accounts",
    )

    is_enabled = models.BooleanField(
        default=True, help_text="Whether the worker should keep this account online."
    )

    class Presence(models.TextChoices):
        AVAILABLE = "available", "Available / online"
        BUSY = "busy", "Busy / away"

    presence = models.CharField(
        max_length=10,
        choices=Presence.choices,
        default=Presence.AVAILABLE,
        help_text="Drives which auto-reply rules fire (online vs busy).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_connected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.label} ({self.phone or self.username or self.pk})"

    # -- credentials helpers -------------------------------------------------
    @property
    def effective_api_id(self) -> int:
        return self.api_id or settings.TELEGRAM_API_ID

    @property
    def effective_api_hash(self) -> str:
        return self.api_hash or settings.TELEGRAM_API_HASH

    # -- session helpers -----------------------------------------------------
    def set_session(self, session_string: str) -> None:
        self.session_enc = encrypt_secret(session_string) if session_string else ""

    def get_session(self) -> str:
        return decrypt_secret(self.session_enc) if self.session_enc else ""

    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username or self.label


class AccountLoginSession(models.Model):
    """
    Transient state for an interactive login flow.

    Telethon's phone-code and QR flows are multi-step. We persist the partial
    StringSession between HTTP requests so the wizard can resume.
    """

    class Stage(models.TextChoices):
        CODE = "code", "Awaiting code"
        PASSWORD = "password", "Awaiting 2FA password"
        QR = "qr", "Awaiting QR scan"
        DONE = "done", "Completed"

    class Method(models.TextChoices):
        PHONE = "phone", "Phone + code"
        QR = "qr", "QR code"

    account = models.ForeignKey(
        TelegramAccount, on_delete=models.CASCADE, related_name="login_sessions"
    )
    method = models.CharField(max_length=8, choices=Method.choices)
    stage = models.CharField(max_length=12, choices=Stage.choices)

    phone = models.CharField(max_length=32, blank=True)
    phone_code_hash = models.CharField(max_length=128, blank=True)

    # Encrypted partial StringSession used to resume the flow.
    session_enc = models.TextField(blank=True, default="")

    # For QR: the tg://login token URL currently displayed.
    qr_url = models.TextField(blank=True, default="")

    error = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def set_session(self, session_string: str) -> None:
        self.session_enc = encrypt_secret(session_string) if session_string else ""

    def get_session(self) -> str:
        return decrypt_secret(self.session_enc) if self.session_enc else ""
