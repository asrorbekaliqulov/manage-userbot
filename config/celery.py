import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("userbot_panel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Periodic jobs. With django-celery-beat's DatabaseScheduler these entries are
# synced into the database on startup; you can then tweak them from the admin.
app.conf.beat_schedule = {
    "dispatch-due-schedules-every-minute": {
        "task": "apps.messaging.tasks.dispatch_due_schedules",
        "schedule": 60.0,
    },
    "scrape-all-sources-every-5-min": {
        "task": "apps.scraping.tasks.scrape_all_sources",
        "schedule": 300.0,
    },
    "refresh-accounts-hourly": {
        "task": "apps.accounts.tasks.refresh_all_accounts",
        "schedule": 3600.0,
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
