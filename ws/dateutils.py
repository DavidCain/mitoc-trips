"""
Some shortcuts to retrieve meaningful dates.
"""

from datetime import datetime, timedelta, time
from django.utils import timezone
from django.conf import settings


def nearest_sat():
    """ Give the date of the nearest Saturday (next week if today is Saturday)

    Because most trips are posted during the week, and occur that weekend,
    defaulting to Saturday is reasonable. (It's rare that a trip posted on
    Saturday is for that day or the next day, so default to next Saturday).
    """
    now = timezone.now()
    if now.weekday() == 5:  # (today is Saturday)
        delta = timedelta(days=7)
    else:  # Nearest Saturday
        delta = timedelta((12 - now.weekday()) % 7)
    return (now + delta).date()


def days_from_now(days=3):
    return timezone.now() + timedelta(days=days)


def wed_at_noon():
    now = timezone.now()
    days_til_wed = timedelta((9 - now.weekday()) % 7)
    wed = (now + days_til_wed)
    return wed.replace(hour=12, minute=0, second=0, microsecond=0)

def participant_cutoff():
    """ Datetime at which previous signups are no longer current/valid. """
    delta = timedelta(settings.MUST_UPDATE_AFTER_DAYS)
    return timezone.now() - delta
