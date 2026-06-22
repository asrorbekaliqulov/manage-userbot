"""API-key authentication for the developer REST API."""
from __future__ import annotations

from rest_framework import authentication, exceptions

from .models import APIKey


class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Authenticate requests using an ``Authorization: Api-Key <key>`` header
    (an ``X-API-Key: <key>`` header is also accepted).

    On success ``request.user`` is the :class:`Developer` and ``request.auth``
    is the :class:`APIKey` instance (so views can check scopes).
    """

    keyword = "Api-Key"

    def authenticate(self, request):
        raw_key = self._extract_key(request)
        if not raw_key:
            return None  # fall through to other authenticators

        key = APIKey.find_valid(raw_key)
        if key is None:
            raise exceptions.AuthenticationFailed("Invalid or expired API key.")

        key.touch()
        return (key.developer, key)

    def _extract_key(self, request) -> str | None:
        header = authentication.get_authorization_header(request).decode("latin-1")
        if header:
            parts = header.split()
            if len(parts) == 2 and parts[0].lower() == self.keyword.lower():
                return parts[1]
        x_api_key = request.META.get("HTTP_X_API_KEY")
        if x_api_key:
            return x_api_key.strip()
        return None

    def authenticate_header(self, request):
        return self.keyword
