import os

import celery
import raven
from raven.contrib.celery import register_signal, register_logger_signal

from django.apps import apps


os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ws.settings')
RAVEN_DSN = os.getenv('RAVEN_DSN')

class Celery(celery.Celery):
    def on_configure(self):
        if not RAVEN_DSN:
            return

        client = raven.Client(RAVEN_DSN)

        # register a custom filter to filter out duplicate logs
        register_logger_signal(client)

        # hook into the Celery error handler
        register_signal(client)

app = Celery('ws')

app.config_from_object('django.conf:settings')

# Workaround for extracting app names (can do more robustly in Celery 4)
app.autodiscover_tasks(lambda: [n.name for n in apps.get_app_configs()])
