"""
Encryption helpers.

Two layers of secrets live in this project:

1. **Session strings** of connected Telegram accounts. These are encrypted at
   rest with a server-wide Fernet key (``settings.ENCRYPTION_KEY``) so that a
   database dump alone cannot be used to hijack accounts.

2. **Private message content** belonging to *developer-owned* accounts. The
   platform operator (admin) must NOT be able to read this data from the panel.
   It is therefore encrypted with a key derived from the developer's API key.
   Only someone holding the API key (the developer, or an admin who was given
   the key) can decrypt it.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _server_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not configured. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a string with the server-wide key (e.g. a session string)."""
    if plaintext is None:
        return ""
    token = _server_fernet().encrypt(plaintext.encode())
    return token.decode()


def decrypt_secret(token: str) -> str:
    """Decrypt a server-key encrypted string."""
    if not token:
        return ""
    return _server_fernet().decrypt(token.encode()).decode()


def fernet_from_api_key(api_key: str) -> Fernet:
    """
    Derive a deterministic Fernet key from a developer API key.

    The same API key always produces the same Fernet key, so content encrypted
    with it can later be decrypted by re-supplying the key.
    """
    digest = hashlib.sha256(api_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_with_api_key(plaintext: str, api_key: str) -> str:
    if plaintext is None:
        plaintext = ""
    return fernet_from_api_key(api_key).encrypt(plaintext.encode()).decode()


def decrypt_with_api_key(token: str, api_key: str) -> str | None:
    """Return decrypted text, or ``None`` if the key is wrong / data corrupt."""
    if not token:
        return ""
    try:
        return fernet_from_api_key(api_key).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None
