from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import TelegramAccount
from apps.logs.models import ActionLog
from apps.messaging.models import AutoReplyRule, Message, ScheduledMessage
from apps.scraping.models import ScrapedPost, ScrapeSource

from .models import APIKeyRequest


def _developer_from_context(context):
    request = context.get("request")
    user = getattr(request, "user", None)
    # Developer principals expose get_content_key(); staff users do not.
    if user is not None and hasattr(user, "get_content_key"):
        return user
    return None


class TelegramAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelegramAccount
        fields = [
            "id", "label", "phone", "username", "first_name", "last_name",
            "status", "presence", "is_private", "is_enabled",
            "last_connected_at", "created_at",
        ]
        read_only_fields = fields


class MessageSerializer(serializers.ModelSerializer):
    text = serializers.SerializerMethodField()
    locked = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id", "account", "direction", "kind", "chat_id", "chat_title",
            "chat_type", "sender_id", "sender_name", "text", "locked",
            "has_media", "media_type", "date",
        ]

    def _content_key(self, obj):
        developer = _developer_from_context(self.context)
        if obj.is_private and obj.account.owner and developer:
            if obj.account.owner_id == developer.pk:
                return developer.get_content_key()
        return None

    def get_text(self, obj):
        return obj.get_content(self._content_key(obj))

    def get_locked(self, obj):
        return obj.is_private and self.get_text(obj) is None


class ScheduledMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduledMessage
        fields = [
            "id", "title", "text", "file_path", "from_mode", "account",
            "targets", "scheduled_for", "silent", "repeat_cron", "status",
            "result_log", "sent_at", "created_at",
        ]
        read_only_fields = ["status", "result_log", "sent_at", "created_at"]


class AutoReplyRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoReplyRule
        fields = [
            "id", "name", "mode", "account", "apply_to_all", "keywords",
            "reply_text", "only_private_chats", "cooldown_minutes",
            "is_active", "created_at",
        ]
        read_only_fields = ["created_at"]


class ScrapeSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapeSource
        fields = [
            "id", "name", "source", "account", "keywords", "match_mode",
            "forward_targets", "auto_forward", "forward_account",
            "extra_caption", "last_message_id", "poll_interval_minutes",
            "is_active", "created_at",
        ]
        read_only_fields = ["last_message_id", "created_at"]


class ScrapedPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScrapedPost
        fields = [
            "id", "source", "tg_message_id", "text", "matched_keywords",
            "has_media", "media_type", "post_date", "forwarded", "forwarded_at",
        ]
        read_only_fields = fields


class ActionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionLog
        fields = [
            "id", "category", "action", "description", "account",
            "source", "metadata", "created_at",
        ]
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    target = serializers.CharField()
    text = serializers.CharField(allow_blank=True, required=False, default="")
    file_path = serializers.CharField(required=False, allow_blank=True)
    silent = serializers.BooleanField(required=False, default=False)


class CreateChannelSerializer(serializers.Serializer):
    title = serializers.CharField()
    about = serializers.CharField(required=False, allow_blank=True, default="")
    megagroup = serializers.BooleanField(required=False, default=False)


class APIKeyRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = APIKeyRequest
        fields = [
            "id", "name", "organization", "email", "telegram_username",
            "reason", "requested_scopes", "delivery_method", "status", "created_at",
        ]
        read_only_fields = ["status", "created_at"]
