from __future__ import annotations

import hashlib
import secrets

from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.crypto import decrypt_secret, encrypt_secret

# Scopes a key may be granted.
API_SCOPES = [
    ("accounts:read", "Read connected accounts"),
    ("accounts:write", "Edit / connect accounts"),
    ("messages:read", "Read messages"),
    ("messages:send", "Send messages"),
    ("schedules", "Manage scheduled messages"),
    ("scraping", "Manage scraping rules & read scraped posts"),
    ("autoreply", "Manage auto-reply rules"),
    ("channels", "Create channels / groups"),
    ("logs:read", "Read action logs"),
]
DEFAULT_SCOPES = [s[0] for s in API_SCOPES]


def _hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


class Developer(models.Model):
    """An external developer / company consuming the API."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="developer_profile",
    )
    name = models.CharField(max_length=150)
    organization = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)

    # Random per-developer Fernet key used to encrypt private message content.
    # Stored encrypted under the server key so the background worker can use it.
    content_key_enc = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.organization or self.name

    def save(self, *args, **kwargs):
        if not self.content_key_enc:
            self.content_key_enc = encrypt_secret(Fernet.generate_key().decode())
        super().save(*args, **kwargs)

    def get_content_key(self) -> str:
        """Return the developer's content Fernet key (decrypted)."""
        return decrypt_secret(self.content_key_enc)

    # DRF treats the developer as the authenticated principal for API requests.
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False


class APIKeyRequest(models.Model):
    """A request from a developer to be issued an API key. Admin approves it."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class Delivery(models.TextChoices):
        EMAIL = "email", "Email"
        TELEGRAM = "telegram", "Telegram"
        BOTH = "both", "Email + Telegram"

    developer = models.ForeignKey(
        Developer, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="key_requests",
    )
    # Applicant details (used to create a Developer on approval if needed).
    name = models.CharField(max_length=150)
    organization = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    reason = models.TextField(blank=True)
    requested_scopes = models.JSONField(default=list, blank=True)
    delivery_method = models.CharField(
        max_length=10, choices=Delivery.choices, default=Delivery.EMAIL
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reviewed_key_requests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"


class APIKey(models.Model):
    """An issued API key. The raw key is shown once and only its hash is stored."""

    developer = models.ForeignKey(
        Developer, on_delete=models.CASCADE, related_name="api_keys"
    )
    label = models.CharField(max_length=120, default="default")
    prefix = models.CharField(max_length=16, db_index=True)
    key_hash = models.CharField(max_length=64, unique=True)
    scopes = models.JSONField(default=list, blank=True)

    request = models.ForeignKey(
        APIKeyRequest, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="issued_keys",
    )
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.label} ({self.prefix}...)"

    @classmethod
    def generate(cls, developer: "Developer", *, label="default", scopes=None,
                 request=None):
        """Create a new key, returning ``(instance, raw_key)``."""
        secret = secrets.token_urlsafe(32)
        prefix = secrets.token_hex(4)  # 8 hex chars
        raw_key = f"ubp_{prefix}_{secret}"
        instance = cls.objects.create(
            developer=developer,
            label=label,
            prefix=prefix,
            key_hash=_hash_key(raw_key),
            scopes=scopes or DEFAULT_SCOPES,
            request=request,
        )
        return instance, raw_key

    @classmethod
    def find_valid(cls, raw_key: str) -> "APIKey | None":
        try:
            key = cls.objects.select_related("developer").get(
                key_hash=_hash_key(raw_key), is_active=True
            )
        except cls.DoesNotExist:
            return None
        if key.expires_at and key.expires_at < timezone.now():
            return None
        if not key.developer or not key.developer.is_active:
            return None
        return key

    def matches(self, raw_key: str) -> bool:
        return self.key_hash == _hash_key(raw_key)

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])

    def touch(self):
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])
