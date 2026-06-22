from django.contrib import admin, messages

from .models import APIKey, APIKeyRequest, Developer
from .services import approve_request, reject_request


@admin.register(Developer)
class DeveloperAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "email", "telegram_username", "is_active")
    search_fields = ("name", "organization", "email", "telegram_username")
    readonly_fields = ("content_key_enc", "created_at")


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("label", "developer", "prefix", "is_active", "last_used_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("label", "prefix", "developer__name")
    readonly_fields = ("prefix", "key_hash", "created_at", "last_used_at")


@admin.register(APIKeyRequest)
class APIKeyRequestAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "status", "delivery_method", "created_at")
    list_filter = ("status", "delivery_method")
    search_fields = ("name", "organization", "email", "telegram_username")
    actions = ["approve", "reject"]

    @admin.action(description="Approve selected requests and issue API keys")
    def approve(self, request, queryset):
        issued = 0
        for req in queryset.filter(status=APIKeyRequest.Status.PENDING):
            key, raw_key = approve_request(req, reviewer=request.user)
            issued += 1
            self.message_user(
                request,
                f"Issued key for {req.name}: {raw_key} (shown once)",
                level=messages.WARNING,
            )
        self.message_user(request, f"Approved {issued} request(s).")

    @admin.action(description="Reject selected requests")
    def reject(self, request, queryset):
        for req in queryset.filter(status=APIKeyRequest.Status.PENDING):
            reject_request(req, reviewer=request.user, note="Rejected from admin")
        self.message_user(request, "Rejected selected request(s).")
