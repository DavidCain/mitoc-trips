"""
WSGI config for ws project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.2/howto/deployment/wsgi/
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ws.settings")

# pylint:disable=wrong-import-position
from django.core.wsgi import get_wsgi_application  # isort:skip  # noqa: E402


application = get_wsgi_application()
