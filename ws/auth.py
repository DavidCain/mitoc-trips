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
        # The maintainer type-annotates their code, but doesn't export types as a form of protest.
        # See: https://github.com/ubernostrum/webcolors/issues/19#issuecomment-1683173415
        return cast(int, api.check_password(password))
    except PwnedPasswordsError:
        # Let Sentry know we had problems, but don't break the flow.
        # Sentry should scrub `password` automatically.
        logger.exception("Encountered an error with django-pwned-passwords")
        return None
