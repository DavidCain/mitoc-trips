"""
Some shortcuts to retrieve meaningful dates.
"""

from datetime import datetime, timedelta, time
from django.utils import timezone
from django.conf import settings


def friday_before(trip_date):
    trip_dow = trip_date.weekday()
    return trip_date - timedelta(days=(trip_dow - 4) % 7)

def local_now():
    return timezone.localtime(timezone.now())


def nearest_sat():
    """ Give the date of the nearest Saturday (next week if today is Saturday)

    Because most trips are posted during the week, and occur that weekend,
    defaulting to Saturday is reasonable. (It's rare that a trip posted on
    Saturday is for that day or the next day, so default to next Saturday).
    """
    now = local_now()
    if now.weekday() == 5:  # (today is Saturday)
        delta = timedelta(days=7)
    else:  # Nearest Saturday
        delta = timedelta((12 - now.weekday()) % 7)
    return (now + delta).date()


def wed_morning():
    now = local_now()
    days_til_wed = timedelta((9 - now.weekday()) % 7)
    wed = (now + days_til_wed)
    return wed.replace(hour=9, minute=0, second=0, microsecond=0)


def closest_wed_at_noon():
    """ Useful in case lottery is run slightly after noon on Wednesday. """
    now = local_now()
    days_til_wed = timedelta((9 - now.weekday()) % 7)
    next_wed = (now + days_til_wed)
    last_wed = next_wed - timedelta(7)

    closest_wed = min([next_wed, last_wed], key=lambda dt: abs(now - dt))
    return closest_wed.replace(hour=12, minute=0, second=0, microsecond=0)


def participant_cutoff():
    """ Datetime at which previous signups are no longer current/valid. """
    delta = timedelta(settings.MUST_UPDATE_AFTER_DAYS)
    return timezone.now() - delta
