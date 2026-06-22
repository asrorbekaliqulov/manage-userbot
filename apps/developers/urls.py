from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.routers import DefaultRouter

from . import api

app_name = "api"

router = DefaultRouter()
router.register("accounts", api.AccountViewSet, basename="account")
router.register("messages", api.MessageViewSet, basename="message")
router.register("schedules", api.ScheduledMessageViewSet, basename="schedule")
router.register("autoreplies", api.AutoReplyRuleViewSet, basename="autoreply")
router.register("scrape-sources", api.ScrapeSourceViewSet, basename="scrape-source")
router.register("scraped-posts", api.ScrapedPostViewSet, basename="scraped-post")
router.register("logs", api.ActionLogViewSet, basename="log")

urlpatterns = [
    # Public: request an API key (admin must approve).
    path("v1/request-key/", api.APIKeyRequestCreateView.as_view(), name="request-key"),
    # OpenAPI schema + interactive docs.
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="swagger"),
    path("redoc/", SpectacularRedocView.as_view(url_name="api:schema"), name="redoc"),
    # Versioned resource endpoints.
    path("v1/", include(router.urls)),
]
