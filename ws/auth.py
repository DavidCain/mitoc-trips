import logging
import re

from django.core.exceptions import ValidationError
from django.utils.translation import ngettext
from pwned_passwords_django.api import pwned_password
from pwned_passwords_django.validators import PwnedPasswordsValidator

from ws import settings

logger = logging.getLogger(__name__)

# As of 2022-08-27, pwned_password sometimes includes commas in `times`
# This hack can go away once the library is updated to handle commas
# https://github.com/ubernostrum/pwned-passwords-django/issues/35
INT_WITH_COMMA = re.compile(
    r"invalid literal for int\(\) with base 10: '(?P<times>[\d,]+)'"
)


def times_seen_in_hibp(password: str) -> int | None:
    """Return times password has been seen in HIBP."""
    if settings.DEBUG and password in settings.WHITELISTED_BAD_PASSWORDS:
        return 0

    try:
        return pwned_password(password)
    except ValueError as err:
        has_comma = INT_WITH_COMMA.match(str(err))
        if not has_comma:
            raise
        return int(has_comma.group('times').replace(',', ''))
    except Exception:  # pylint: disable=broad-except
        # Let Sentry know we had problems, but don't break the flow.
        # Sentry should scrub `password` automatically.
        logger.exception("Encountered an error with django-pwned-passwords")
        return None


class CommaPwnedPasswordsValidator(PwnedPasswordsValidator):
    """Temporarily work around an issue with `pwned-passwords-django`.

    This prevents 500s when trying to sign up with a very common password.
    Specifically, if a comma is found in the count of times the password is
    seen, we should fix the parsing to an integer.
    """

    def validate(self, password, user=None):
        try:
            super().validate(password, user=user)
        except ValueError as err:
            has_comma = INT_WITH_COMMA.match(str(err))
            if not has_comma:
                raise

            amount = int(has_comma.group('times').replace(',', ''))
            raise ValidationError(  # pylint:disable=raise-missing-from
                ngettext(
                    self.error_message["singular"], self.error_message["plural"], amount
                ),
                params={"amount": amount},
                code="pwned_password",
            )
