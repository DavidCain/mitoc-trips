# Import this eagerly when Django starts so tasks will use the initialized app
from .celery_config import app as celery_app
