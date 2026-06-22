from django.contrib import admin

from .models import ActionLog


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "category", "action", "account", "developer", "source")
    list_filter = ("category", "source", "created_at")
    search_fields = ("action", "description")
    readonly_fields = [f.name for f in ActionLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
