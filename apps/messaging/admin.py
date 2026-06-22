from django.contrib import admin

from .models import (
    AutoReplyRule,
    AutoReplyState,
    Message,
    ScheduledMessage,
)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("date", "account", "direction", "kind", "chat_title", "is_private")
    list_filter = ("direction", "kind", "is_private", "account")
    search_fields = ("chat_title", "sender_name", "text")
    readonly_fields = ("text_enc",)


@admin.register(ScheduledMessage)
class ScheduledMessageAdmin(admin.ModelAdmin):
    list_display = ("title", "from_mode", "account", "scheduled_for", "status")
    list_filter = ("status", "from_mode")


@admin.register(AutoReplyRule)
class AutoReplyRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "mode", "account", "apply_to_all", "is_active")
    list_filter = ("mode", "apply_to_all", "is_active")


admin.site.register(AutoReplyState)
