# Userbot Panel

A Django admin panel for managing Telegram **userbots** (real user accounts via
MTProto / Telethon) — built for companies that need to operate many accounts
from one place, plus a developer API so customers can automate everything from
code.

## Features

- **Connect accounts** via login code (phone) **or QR code**, including
  **two-step verification (2FA)** when enabled.
- **Receive & view messages** of every type Telegram supports (text, photo,
  video, voice, audio, documents, stickers, GIFs, contacts, locations, polls…).
- **Edit accounts** and toggle their presence (online vs busy).
- **Scheduler** — send a message at a chosen time to one or many targets
  (users / channels / groups), **from a single account or from all accounts**.
- **Channel scraping** — watch channels by **keyword**, store matched posts in
  the database, and **auto-forward** them to other channels/groups.
- **Create channels / supergroups** straight from the panel.
- **Auto-reply** — reply automatically to incoming DMs, per-account or for all
  accounts, with online / busy modes and keyword triggers.
- **Developer API + API keys** — developers request a key, an admin approves it,
  and the key is delivered over **Telegram and/or email**. Interactive docs
  (Swagger / ReDoc) plus a human-readable docs page are included.
- **Privacy + full audit log** — developer-owned accounts can be marked
  *private*: their message content is encrypted with the developer's key and the
  admin cannot read it from the panel without that key. Meanwhile **every
  action is logged** (logins, edits, messages sent, channels created, etc.).

## Architecture

```
config/                Django project (settings, urls, celery, wsgi/asgi)
apps/
  accounts/            TelegramAccount model + Telethon client/auth/actions + worker
  messaging/           Messages, scheduler, auto-reply
  scraping/            Keyword channel scraping & forwarding
  developers/          Developer accounts, API keys, REST API, docs
  logs/                Immutable audit trail
  dashboard/           Admin panel UI (Django templates)
  common/              Shared crypto helpers
templates/ static/     UI templates and styles
```

Processes:

| Process | Command | Purpose |
|---------|---------|---------|
| Web | `python manage.py runserver` | Admin panel + REST API |
| Worker | `python manage.py run_userbots` | Keeps accounts online, receives messages, auto-replies |
| Celery worker | `celery -A config worker -l info` | Scheduled sends, scraping |
| Celery beat | `celery -A config beat -l info` | Periodic triggers |

## Setup

> Requires Python 3.11+, and (for background jobs) Redis.

```bash
# 1. Install dependencies
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Generate an encryption key and put it in ENCRYPTION_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Add your Telegram API credentials (https://my.telegram.org) as
# TELEGRAM_API_ID / TELEGRAM_API_HASH.

# 3. Migrate & create an admin user
python manage.py migrate
python manage.py createsuperuser

# 4. Run
python manage.py runserver           # panel at http://127.0.0.1:8000/
python manage.py run_userbots        # (separate terminal) live accounts

# 5. Background jobs (optional, needs Redis)
celery -A config worker -l info
celery -A config beat -l info
```

Log in at `/login/`, then **Accounts → Connect account** to add your first
userbot. Django's own admin lives at `/django-admin/`.

## Developer API

- Request a key: `POST /api/v1/request-key/`
- Approve it in the panel: **Developers → Key requests**
- Authenticate with `Authorization: Api-Key <key>`
- Interactive docs: `/api/docs/` (Swagger) and `/api/redoc/`
- In-panel guide: **API docs**

## Security notes

- Session strings are encrypted at rest with `ENCRYPTION_KEY` (Fernet).
- Private account content is encrypted with a per-developer content key; the
  panel only decrypts it when a valid API key is supplied.
- The audit log is append-only from the UI.
- Treat Telegram session strings like passwords — anyone with them controls the
  account. Keep `ENCRYPTION_KEY` and your database secure.
