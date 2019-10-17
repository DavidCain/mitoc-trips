"""
Some shortcuts to retrieve meaningful dates.
"""

from datetime import datetime, time, timedelta

from django.utils import timezone


def date_from_iso(datestring):
    """ Convert a YYYY-MM-DD datestring to a date object.

    Throws ValueError or TypeError on invalid inputs.
    """
    # Might throw ValueError or TypeError
    moment = datetime.strptime(datestring, '%Y-%m-%d')
    return moment.date()


def localize(dt_time):
    """ Take a naive datetime and assign a time zone to it (without changing wall time).

    >>> from datetime import datetime
    >>> localize(datetime(2018, 10, 27, 4, 30)
    datetime.datetime(2018, 10, 27, 4, 30, tzinfo=<DstTzInfo 'America/New_York' EDT-1 day, 20:00:00 DST>)
    """
    pytz_timezone = timezone.get_default_timezone()
    return pytz_timezone.localize(dt_time)


def itinerary_available_at(trip_date):
    """ Return the date & time at which the trip's itinerary may be submitted.

    We disallow submitting an itinerary too far in advance because weather
    changes, participants may be added/removed, and drivers may change. Only
    allowing itineraries to be submitted close to the start of a trip ensures
    the description is more accurate.
    """
    trip_dow = trip_date.weekday()
    thursday_before = trip_date - timedelta(days=(trip_dow - 3) % 7)
    thursday_evening = datetime.combine(thursday_before, time(18, 0))
    return localize(thursday_evening)


def late_at_night(date):
    """ 23:59 on the date, since midnight is technically the next day. """
    dt = datetime(date.year, date.month, date.day, 23, 59, 59)
    return localize(dt)


def fcfs_close_time(trip_date):
    """ The time that a WS trip should close its first-come, first-serve signups.

    Winter School trips that are part of the weekly lottery typically take
    place on Saturday & Sunday (and occasionally Friday or Monday). After
    the Wednesday morning lottery runs, we have a period of being open for
    first-come, first-serve signups. This method returns when those signups
    should close.

    In normal circumstances, WS trips close for all signups on Thursday night.
    """
    trip_dow = trip_date.weekday()
    thur_before = trip_date - timedelta(days=(trip_dow - 3) % 7)

    # Any trip taking place on a Thursday should close on Wednesday night
    # (Otherwise, we would have signups close *after* the trip participants return home)
    if thur_before == trip_date:
        thur_before -= timedelta(days=1)

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
    return lottery_morning


def next_wednesday():
    now = local_now()
    days_til_wed = timedelta((9 - now.weekday()) % 7)
    return now + days_til_wed


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
    ret = datetime.combine(closest_wed, datetime.min.time().replace(hour=12))
    return localize(ret)


def is_winter_school():
    """ Returns if Winter School is ongoing.

    Used to give warnings about lottery preferences and such.

    Should likely be combined with `ws_lectures_complete` or other means of inspecting
    presence of trips this year (that will give a more authoritative picture of whether
    or not Winter School is actually ongoing.
    """
    # Warning: This is only approximate! We cannot define when IAP occurs each year
    now = local_now()
    return now.month == 1 or (now.month == 2 and now.day < 7)


def ws_year():
    """ Returns the year of the nearest Winter School. """
    this_year = local_now().year
    return this_year if local_now().month <= 6 else this_year + 1


def jan_1():
    jan_1st = timezone.datetime(local_date().year, 1, 1)
    return localize(jan_1st)


def default_signups_close_at():
    """ Return the default for when signups should close.

    This is mostly written to give reasonable defaults for Winter School, where all
    trips are posted during the week, for the coming weekend (and should close at 9 am
    on Wednesday, so the lottery can run). However, this is also a sensible assumption
    to make year-round!

    If it's currently late in the week (~Thursday), we could very well be
    posting a last-minute trip for the weekend, though we don't know what the leader
    will choose once creating the initial form defaults. If a trip is being posted on
    Wednesday, then just default to having signups close at midnight before, so we
    don't give a form pre-filled with invalid defaults.
    """
    wed_before = wed_morning()
    if wed_before >= local_now():
        return wed_before

    # If today is Wednesday, just have signups close at midnight before
    trip_date = nearest_sat()
    return late_at_night(trip_date - timedelta(days=1))
