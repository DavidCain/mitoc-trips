import logging
import os

import raven

logger = logging.getLogger(__name__)

RAVEN_DSN = os.getenv('RAVEN_DSN')
client = raven.Client(RAVEN_DSN) if RAVEN_DSN else None


def message(body, context):
    if client:
        client.captureMessage(body, **context)
    logger.error(body)
