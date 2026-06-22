"""Scope-based permissions for API views."""
from __future__ import annotations

from rest_framework import permissions

from .models import APIKey


class HasAPIScope(permissions.BasePermission):
    """Require the API key to carry a given scope.

    Set ``required_scope`` on the view (or ``required_scopes`` for several).
    Session-authenticated staff users bypass scope checks.
    """

    message = "Your API key does not have the required scope."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user and getattr(user, "is_staff", False):
            return True

        auth = getattr(request, "auth", None)
        if not isinstance(auth, APIKey):
            return False

        required = getattr(view, "required_scopes", None)
        single = getattr(view, "required_scope", None)
        if single:
            required = [single]
        if not required:
            return True
        return all(auth.has_scope(scope) for scope in required)
