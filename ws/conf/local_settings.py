"""
Local settings, intended for use on a local computer for basic
feature testing.

  - Exposed secret key
  - DEBUG enabled
  - Project root is just '/'
  - Send emails to console
"""
from typing import Any

DEBUG = True
ALLOWED_HOSTS = ["*"]

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Don't send emails to verify email addresses (rapid account creation)
ACCOUNT_EMAIL_VERIFICATION = "none"


DEBUG_TOOLBAR_PATCH_SETTINGS = False
INTERNAL_IPS = ["127.0.0.1", "192.168.33.15"]


# Tell Celery to only attempt once, then immediately give up.
# (by default, Celery will retry forever)
# This makes development faster when running with no local broker
CELERY_BROKER_TRANSPORT_OPTIONS: dict[str, Any] = {"max_retries": 0}

# Any participant with the password 'foobar' need not hit the HIBP API to check if pwned.
# (we know it's pwned, and it should never be allowed in production, but it's fine locally)
ALLOWED_BAD_PASSWORDS: tuple[str, ...] = ("foobar",)
