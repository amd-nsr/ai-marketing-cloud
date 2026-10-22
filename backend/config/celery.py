"""Celery application shared by the worker and the beat scheduler processes."""

import logging.config
import os
from typing import Any

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("ai_marketing_cloud")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def configure_logging(**kwargs: Any) -> None:
    """Use Django's LOGGING for workers so API and job logs share one format."""
    from django.conf import settings

    logging.config.dictConfig(settings.LOGGING)
