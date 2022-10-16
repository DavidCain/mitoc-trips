"""
A simple module for creating tokens to let users unsubscribe.

Ideally, participants just control their email preferences directly.
However, we provide this method for single-click unsubscribe links.
"""
import enum
from datetime import timedelta
from typing import NamedTuple, Optional, TypedDict

from django.conf import settings
from django.core import signing

from ws import models


class InvalidToken(Exception):
    """An exception class whose message can be given directly to end users."""


class EmailType(enum.IntEnum):
    """Describe a class of automated emails we may send users."""

    # Once (at most) yearly reminders to renew membership
    membership_renewal = 0


class UnsubscribeTarget(NamedTuple):
    """The participant who wishes to unsubscribe, and the emails they should stop getting."""

    participant_pk: int
    email_types: set[EmailType]


class TokenPayload(TypedDict):
    """A JSON-serializable payload to be put into (or extracted from) a signed token."""

    # The participant's primary key
    pk: int

    # An unordered list of email types to unsubscribe from (duplicates will be ignored)
    # Note that these are just the primitive ints behind `EmailType`
    # TODO: how can I properly annotate "not instances of the enum, but the values?"
    emails: list[int]


def _get_signer(key: Optional[str] = None) -> signing.TimestampSigner:
    """Return an object that can be used to either sign payloads or verify & decode."""
    return signing.TimestampSigner(
        # Assuming we're using Django's cryptography APIs securely (and a secret key with high entropy),
        # it should be safe to use the default SECRET_KEY.
        # However, the consequences of failure are high, so use a secret specific to resetting.
        key=key or settings.UNSUBSCRIBE_SECRET_KEY,
        # Salting our payload helps ensure that signed values are used *only* for unsubscribing.
        # We wouldn't want the generated token to be valid for any other use.
        # The tokens that are used to reset passwords in Django, for example, are salted.
        #
        # > Using salt in this way puts the different signatures into different
        # > namespaces. A signature that comes from one namespace (a particular salt
        # > value) cannot be used to validate the same plaintext string in a different
        # > namespace that is using a different salt setting.
        # https://docs.djangoproject.com/en/3.2/topics/signing/
        salt='ws.email.unsubscribe',
        algorithm='sha256',
    )


def generate_unsubscribe_token(participant: models.Participant) -> str:
    """Generate a token to unsubscribe the participant from emails.

    The expectation is that this token will be used in a URL that can
    be accessed even if the participant isn't logged in.
    """
    payload: TokenPayload = {
        'pk': participant.pk,
        'emails': [EmailType.membership_renewal.value],
    }
    return _get_signer().sign_object(payload)


def unsign_token(token: str) -> UnsubscribeTarget:
    """Extract the participant & desired unsubscribe topics from a signed payload.

    Raises:
        signing.SignatureExpired: Token is >30 days old
        signing.BadSignature: Token is invalid (or just >30 days old)
    """
    payload: TokenPayload = _get_signer().unsign_object(
        token,
        # We can tolerate a very long max age.
        # This is because users may take a while to click the link in their email.
        max_age=timedelta(days=30),
    )

    return UnsubscribeTarget(
        participant_pk=payload['pk'],
        email_types={EmailType(email_id) for email_id in payload['emails']},
    )


def _bad_token_reason(exception: signing.BadSignature) -> str:
    """Give a human-readable explanation for what's wrong with the token."""
    if isinstance(exception, signing.SignatureExpired):
        return 'Token expired'
    return 'Invalid token'


def unsubscribe_from_token(token: str) -> models.Participant:
    """Attempt to unsubscribe the participant based on an (assumed valid) token.

    Raises:
        InvalidToken: Expired token, invalid token, or participant gone
    """
    # Any exceptions this method raises have messages meant to be consumed by humans.
    # We don't need the full traceback.
    # pylint:disable=raise-missing-from

    try:
        target = unsign_token(token)
    except signing.BadSignature as e:
        raise InvalidToken(f"{_bad_token_reason(e)}, cannot unsubscribe automatically.")

    try:
        par = models.Participant.objects.get(pk=target.participant_pk)  # Might raise!
    except models.Participant.DoesNotExist:
        raise InvalidToken("Participant no longer exists")

    if EmailType.membership_renewal in target.email_types:
        par.send_membership_reminder = False
    par.save()
    return par
