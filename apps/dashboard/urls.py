from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    # Auth
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="dashboard/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # Home
    path("", views.home, name="home"),

    # Accounts
    path("accounts/", views.accounts, name="accounts"),
    path("accounts/connect/", views.connect_start, name="connect_start"),
    path("accounts/connect/code/<int:session_id>/", views.connect_code, name="connect_code"),
    path("accounts/connect/password/<int:session_id>/", views.connect_password, name="connect_password"),
    path("accounts/connect/qr/<int:session_id>/", views.connect_qr, name="connect_qr"),
    path("accounts/connect/qr/<int:session_id>/poll/", views.connect_qr_poll, name="connect_qr_poll"),
    path("accounts/<int:pk>/", views.account_detail, name="account_detail"),
    path("accounts/<int:pk>/edit/", views.account_edit, name="account_edit"),
    path("accounts/<int:pk>/presence/", views.account_presence, name="account_presence"),
    path("accounts/<int:pk>/disconnect/", views.account_disconnect, name="account_disconnect"),

    # Messages
    path("messages/", views.messages_view, name="messages"),
    path("messages/unlock/", views.unlock_messages, name="unlock_messages"),

    # Schedules
    path("schedules/", views.schedules, name="schedules"),
    path("schedules/new/", views.schedule_create, name="schedule_create"),
    path("schedules/<int:pk>/send/", views.schedule_send_now, name="schedule_send_now"),
    path("schedules/<int:pk>/cancel/", views.schedule_cancel, name="schedule_cancel"),

    # Auto-reply
    path("autoreplies/", views.autoreplies, name="autoreplies"),
    path("autoreplies/new/", views.autoreply_create, name="autoreply_create"),
    path("autoreplies/<int:pk>/toggle/", views.autoreply_toggle, name="autoreply_toggle"),

    # Scraping
    path("scraping/", views.scrape_sources, name="scrape_sources"),
    path("scraping/new/", views.scrape_source_create, name="scrape_source_create"),
    path("scraping/<int:pk>/run/", views.scrape_run, name="scrape_run"),
    path("scraping/<int:pk>/posts/", views.scrape_posts, name="scrape_posts"),

    # Channels
    path("channels/new/", views.create_channel, name="create_channel"),

    # Developers
    path("developers/", views.developers, name="developers"),
    path("developers/requests/", views.key_requests, name="key_requests"),
    path("developers/requests/<int:pk>/approve/", views.key_request_approve, name="key_request_approve"),
    path("developers/requests/<int:pk>/reject/", views.key_request_reject, name="key_request_reject"),

    # Logs
    path("logs/", views.logs, name="logs"),

    # API docs
    path("api-docs/", views.api_docs, name="api_docs"),
]
