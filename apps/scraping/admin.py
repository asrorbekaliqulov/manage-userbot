from django.contrib import admin

from .models import ScrapedPost, ScrapeSource


@admin.register(ScrapeSource)
class ScrapeSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source", "account", "auto_forward", "is_active", "last_message_id")
    list_filter = ("is_active", "auto_forward")
    search_fields = ("name", "source")


@admin.register(ScrapedPost)
class ScrapedPostAdmin(admin.ModelAdmin):
    list_display = ("source", "tg_message_id", "post_date", "forwarded")
    list_filter = ("forwarded", "source")
    search_fields = ("text",)
