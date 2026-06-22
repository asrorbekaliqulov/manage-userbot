from django.contrib import admin

from .models import AccountLoginSession, TelegramAccount


@admin.register(TelegramAccount)
class TelegramAccountAdmin(admin.ModelAdmin):
    list_display = (
        "label",
        "phone",
        "username",
        "status",
        "is_2fa_enabled",
        "is_private",
        "owner",
        "is_enabled",
        "last_connected_at",
    )
    list_filter = ("status", "is_2fa_enabled", "is_private", "is_enabled")
    search_fields = ("label", "phone", "username", "first_name", "last_name")
    readonly_fields = ("session_enc", "telegram_user_id", "created_at", "updated_at")


@admin.register(AccountLoginSession)
class AccountLoginSessionAdmin(admin.ModelAdmin):
    list_display = ("account", "method", "stage", "created_at", "updated_at")
    list_filter = ("method", "stage")
