"""
Some shortcuts to retrieve meaningful dates.
"""

from datetime import datetime, timedelta
from django.utils import timezone
from django.conf import settings


def friday_before(trip_date):
    trip_dow = trip_date.weekday()
    return trip_date - timedelta(days=(trip_dow - 4) % 7)


def late_at_night(date):
    """ 23:59 on the date, since midnight is technically the next day. """
    return timezone.datetime(date.year, date.month, date.day, 23, 59, 59)


def fcfs_close_time(trip_date):
    """ WS trips close first-come, first-serve signups on Thursday night. """
    trip_dow = trip_date.weekday()
    thur_before = trip_date - timedelta(days=(trip_dow - 3) % 7)
    return late_at_night(thur_before)


def local_now():
    return timezone.localtime(timezone.now())


def local_date():
    return local_now().date()


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


def lottery_time(lottery_date):
    """ Given a date, return the datetime when lottery trips should close.

    If change the lottery time, modify just this method (others depend on it)
    """
    return lottery_date.replace(hour=9, minute=0, second=0, microsecond=0)


def next_lottery():
    lottery_morning = wed_morning()  # Closest Wednesday, at 9 am
    if local_now() > lottery_morning:  # Today is Wednesday, after lottery
        return lottery_time(lottery_morning + timedelta(days=7))
    else:
        return lottery_morning


def next_wednesday():
    now = local_now()
    days_til_wed = timedelta((9 - now.weekday()) % 7)
    return (now + days_til_wed)


def wed_morning():
    return lottery_time(next_wednesday())


def closest_wednesday():
    now = local_now()
    next_wed = next_wednesday()
    last_wed = next_wed - timedelta(7)
    return min([next_wed, last_wed], key=lambda dt: abs(now - dt)).date()


def closest_wed_at_noon():
    """ Useful in case lottery is run slightly after noon on Wednesday. """
    closest_wed = closest_wednesday()
    return datetime.combine(closest_wed, datetime.min.time().replace(hour=12))


def participant_cutoff():
    """ Datetime at which previous signups are no longer current/valid. """
    delta = timedelta(settings.MUST_UPDATE_AFTER_DAYS)
    return timezone.now() - delta


def is_winter_school():
    """ Returns if Winter School is ongoing.

    Used to give warnings about lottery preferences and such.
    """
    # Approximate -programming for IAP is difficult
    now = local_now()
    return now.month == 1 or (now.month == 2 and now.day < 7)


def ws_year():
    """ Returns the year of the nearest Winter School. """
    this_year = local_now().year
    return this_year if local_now().month <= 6 else this_year + 1


def jan_1():
    pytz_timezone = timezone.get_default_timezone()
    jan_1st = timezone.datetime(local_date().year, 1, 1)
    return pytz_timezone.localize(jan_1st)
