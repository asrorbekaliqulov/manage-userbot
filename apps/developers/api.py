from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import TelegramAccount
from apps.accounts.telegram.actions import (
    create_channel,
    fetch_dialogs,
    fetch_history,
    send_message,
)
from apps.logs.models import ActionLog
from apps.logs.services import log_action
from apps.messaging.models import AutoReplyRule, Message, ScheduledMessage
from apps.scraping.models import ScrapedPost, ScrapeSource

from .permissions import HasAPIScope
from .serializers import (
    ActionLogSerializer,
    AutoReplyRuleSerializer,
    CreateChannelSerializer,
    MessageSerializer,
    ScheduledMessageSerializer,
    ScrapedPostSerializer,
    ScrapeSourceSerializer,
    SendMessageSerializer,
    TelegramAccountSerializer,
)


def _developer(request):
    user = getattr(request, "user", None)
    if user is not None and hasattr(user, "get_content_key"):
        return user
    return None


class OwnerScopedMixin:
    """Limit querysets to the authenticated developer's own objects."""

    owner_field = "owner"

    def get_queryset(self):
        qs = super().get_queryset()
        developer = _developer(self.request)
        if developer is None:  # staff session user sees everything
            return qs
        return qs.filter(**{self.owner_field: developer})

    def perform_create(self, serializer):
        developer = _developer(self.request)
        serializer.save(owner=developer)


class AccountViewSet(OwnerScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = TelegramAccount.objects.all()
    serializer_class = TelegramAccountSerializer
    permission_classes = [HasAPIScope]
    required_scope = "accounts:read"

    @action(detail=True, methods=["post"], url_path="send-message")
    def send_message(self, request, pk=None):
        if not self._scope(request, "messages:send"):
            return Response({"detail": "scope messages:send required"}, status=403)
        account = self.get_object()
        s = SendMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        result = send_message(
            account.get_session(),
            account.effective_api_id,
            account.effective_api_hash,
            s.validated_data["target"],
            s.validated_data.get("text", ""),
            file_path=s.validated_data.get("file_path") or None,
            silent=s.validated_data.get("silent", False),
        )
        log_action(
            category="message",
            action="api_send_message",
            account=account,
            developer=account.owner,
            source="api",
            metadata={"target": s.validated_data["target"], "ok": result.get("ok")},
            ip_address=getattr(request, "client_ip", None),
        )
        code = status.HTTP_200_OK if result.get("ok") else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)

    @action(detail=True, methods=["post"], url_path="create-channel")
    def create_channel(self, request, pk=None):
        if not self._scope(request, "channels"):
            return Response({"detail": "scope channels required"}, status=403)
        account = self.get_object()
        s = CreateChannelSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        result = create_channel(
            account.get_session(),
            account.effective_api_id,
            account.effective_api_hash,
            s.validated_data["title"],
            s.validated_data.get("about", ""),
            megagroup=s.validated_data.get("megagroup", False),
        )
        log_action(
            category="channel",
            action="api_create_channel",
            account=account,
            developer=account.owner,
            source="api",
            metadata={"title": s.validated_data["title"], "ok": result.get("ok")},
            ip_address=getattr(request, "client_ip", None),
        )
        return Response(result)

    @action(detail=True, methods=["get"])
    def dialogs(self, request, pk=None):
        account = self.get_object()
        result = fetch_dialogs(
            account.get_session(), account.effective_api_id, account.effective_api_hash
        )
        return Response(result)

    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        if not self._scope(request, "messages:read"):
            return Response({"detail": "scope messages:read required"}, status=403)
        account = self.get_object()
        target = request.query_params.get("target")
        if not target:
            return Response({"detail": "target query param required"}, status=400)
        result = fetch_history(
            account.get_session(),
            account.effective_api_id,
            account.effective_api_hash,
            target,
            limit=int(request.query_params.get("limit", 50)),
        )
        return Response(result)

    @staticmethod
    def _scope(request, scope):
        auth = getattr(request, "auth", None)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_staff", False):
            return True
        return bool(auth and hasattr(auth, "has_scope") and auth.has_scope(scope))


class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Message.objects.select_related("account", "account__owner").all()
    serializer_class = MessageSerializer
    permission_classes = [HasAPIScope]
    required_scope = "messages:read"

    def get_queryset(self):
        qs = super().get_queryset()
        developer = _developer(self.request)
        if developer is not None:
            qs = qs.filter(account__owner=developer)
        account_id = self.request.query_params.get("account")
        if account_id:
            qs = qs.filter(account_id=account_id)
        return qs


class ScheduledMessageViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = ScheduledMessage.objects.all()
    serializer_class = ScheduledMessageSerializer
    permission_classes = [HasAPIScope]
    required_scope = "schedules"


class AutoReplyRuleViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = AutoReplyRule.objects.all()
    serializer_class = AutoReplyRuleSerializer
    permission_classes = [HasAPIScope]
    required_scope = "autoreply"


class ScrapeSourceViewSet(OwnerScopedMixin, viewsets.ModelViewSet):
    queryset = ScrapeSource.objects.all()
    serializer_class = ScrapeSourceSerializer
    permission_classes = [HasAPIScope]
    required_scope = "scraping"


class ScrapedPostViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ScrapedPost.objects.select_related("source").all()
    serializer_class = ScrapedPostSerializer
    permission_classes = [HasAPIScope]
    required_scope = "scraping"

    def get_queryset(self):
        qs = super().get_queryset()
        developer = _developer(self.request)
        if developer is not None:
            qs = qs.filter(source__owner=developer)
        source_id = self.request.query_params.get("source")
        if source_id:
            qs = qs.filter(source_id=source_id)
        return qs


class ActionLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ActionLog.objects.select_related("account").all()
    serializer_class = ActionLogSerializer
    permission_classes = [HasAPIScope]
    required_scope = "logs:read"

    def get_queryset(self):
        qs = super().get_queryset()
        developer = _developer(self.request)
        if developer is not None:
            from django.db.models import Q

            qs = qs.filter(Q(developer=developer) | Q(account__owner=developer))
        return qs



from rest_framework import generics
from rest_framework.permissions import AllowAny

from apps.logs.services import log_action as _log_action
from .models import APIKeyRequest
from .serializers import APIKeyRequestSerializer


class APIKeyRequestCreateView(generics.CreateAPIView):
    """Public endpoint developers use to request an API key (admin approves)."""

    queryset = APIKeyRequest.objects.all()
    serializer_class = APIKeyRequestSerializer
    permission_classes = [AllowAny]
    authentication_classes = []

    def perform_create(self, serializer):
        req = serializer.save(status=APIKeyRequest.Status.PENDING)
        _log_action(
            category="developer",
            action="api_key_requested",
            description=f"API key requested by {req.name}",
            source="api",
            metadata={"email": req.email, "telegram": req.telegram_username},
            ip_address=getattr(self.request, "client_ip", None),
        )
