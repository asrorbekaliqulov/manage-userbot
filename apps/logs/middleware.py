"""Attach the client IP to the request so views/services can log it."""
from __future__ import annotations


def get_client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class RequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.client_ip = get_client_ip(request)
        return self.get_response(request)
