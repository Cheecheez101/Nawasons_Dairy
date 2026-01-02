"""Celery application instance for the Nawa Sons Dairy project."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nawasons_dairy.settings")

app = Celery("nawasons_dairy")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):  # pragma: no cover - convenience helper
    print(f"Request: {self.request!r}")
