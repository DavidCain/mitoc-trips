import logging
from typing import cast

from pwned_passwords_django import api
from pwned_passwords_django.exceptions import PwnedPasswordsError

from ws import settings

logger = logging.getLogger(__name__)


def times_seen_in_hibp(password: str) -> int | None:
    """Return times password has been seen in HIBP."""
    if settings.DEBUG and password in settings.ALLOWED_BAD_PASSWORDS:
        return 0

    try:
        # Package doesn't (yet?) export types.
        # See: https://github.com/ubernostrum/pwned-passwords-django/pull/38
        return cast(int, api.check_password(password))
    except PwnedPasswordsError:
        # Let Sentry know we had problems, but don't break the flow.
        # Sentry should scrub `password` automatically.
        logger.exception("Encountered an error with django-pwned-passwords")
        return None
