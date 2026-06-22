"""
Django settings for the Userbot Panel project.

Configuration is driven by environment variables (see .env.example).
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["127.0.0.1", "localhost"]),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
)

# Read .env file if present
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# ------------------------------------------------------------------
# Core
# ------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "drf_spectacular",
    "django_celery_beat",
    # Local apps
    "apps.accounts",
    "apps.messaging",
    "apps.scraping",
    "apps.developers",
    "apps.logs",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Local
    "apps.logs.middleware.RequestLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.dashboard.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ------------------------------------------------------------------
# Database
# ------------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "dashboard:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "dashboard:login"

# ------------------------------------------------------------------
# Internationalization
# ------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="UTC")
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------------
# Static & media
# ------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------
# Encryption (session strings & private message content at rest)
# ------------------------------------------------------------------
ENCRYPTION_KEY = env("ENCRYPTION_KEY", default="")

# ------------------------------------------------------------------
# Telegram
# ------------------------------------------------------------------
TELEGRAM_API_ID = env.int("TELEGRAM_API_ID", default=0)
TELEGRAM_API_HASH = env("TELEGRAM_API_HASH", default="")
NOTIFIER_ACCOUNT_PHONE = env("NOTIFIER_ACCOUNT_PHONE", default="")

# Where Telethon stores live session files for the worker process.
TELETHON_SESSION_DIR = BASE_DIR / "var" / "sessions"

# ------------------------------------------------------------------
# Celery
# ------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_TRACK_STARTED = True

# ------------------------------------------------------------------
# Email
# ------------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@userbot-panel.local")

# ------------------------------------------------------------------
# Django REST Framework + OpenAPI
# ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.developers.authentication.APIKeyAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Userbot Panel Developer API",
    "DESCRIPTION": "Programmatic access to manage Telegram userbot accounts, "
    "messages, schedules, scraping rules and auto-replies.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}
