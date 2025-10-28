"""Test settings

Intended to mirror production as much as is possible.
"""

from typing import Any

DEBUG = False

ALLOWED_HOSTS = ["*"]

ADMINS = (("David Cain", "davidjosephcain@gmail.com"),)

ACCOUNT_EMAIL_VERIFICATION = "mandatory"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

CORS_ORIGIN_WHITELIST = ("https://mitoc.mit.edu",)
CORS_ALLOW_METHODS = ("GET",)


# Tell Celery to only attempt once, then immediately give up.
# This makes tests faster
CELERY_BROKER_TRANSPORT_OPTIONS: dict[str, Any] = {"max_retries": 0}

# Use the fast (but wildly insecure) MD5 to speed up tests.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# We won't run `collectstatic` before executing tests.
# `strict_manifest` doesn't seem to stop ValueError from being raised on non-found assets.
# As a workaround, just use the default storage instead.
# TODO: Figure out what's going on here, ideally after moving off django-pipeline
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
