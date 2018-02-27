import os

import celery
from raven.contrib.celery import register_signal, register_logger_signal

from django.apps import apps
from ws.sentry import client


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ws.settings')


class Celery(celery.Celery):
    def on_configure(self):
        if not client:
            return

        # register a custom filter to filter out duplicate logs
        register_logger_signal(client)

        # hook into the Celery error handler
        register_signal(client)


app = Celery('ws')

app.config_from_object('django.conf:settings')

# Workaround for extracting app names (can do more robustly in Celery 4)
app.autodiscover_tasks(lambda: [n.name for n in apps.get_app_configs()])
