"""Some shortcuts to retrieve meaningful dates."""

from datetime import date, datetime, time, timedelta

from django.utils import timezone

# TODO: stop importing `models` here! Refactor.
from ws import enums, models  # pylint:disable=cyclic-import


def localize(dt_time: datetime) -> datetime:
    """Take a naive datetime and assign a time zone to it (without changing wall time).

    >>> from datetime import datetime
    >>> localize(datetime(2018, 10, 27, 4, 30)
    datetime.datetime(2018, 10, 27, 4, 30, tzinfo=<DstTzInfo 'America/New_York' EDT-1 day, 20:00:00 DST>)
    """
    return timezone.make_aware(dt_time, timezone.get_default_timezone())


def itinerary_available_at(trip_date: date) -> datetime:
    """Return the date & time at which the trip's itinerary may be submitted.

    We *always* require that the itinerary open at least 24 hours before departure.
    The general assumption is that most trips leave on the weekend, and 6 pm
    on Thursday is a good time to open up itinerary submission.

    We disallow submitting an itinerary too far in advance because weather
    changes, participants may be added/removed, and drivers may change. Only
    allowing itineraries to be submitted close to the start of a trip ensures
    the description is more accurate.
    """
    trip_dow = trip_date.weekday()

    # Most trips are on the weekend (or on Monday, when a holiday). Thursday is ideal.
    thur_before = trip_date - timedelta(days=(trip_dow - 3) % 7)

    # For midweek trips (Wed, Thursday, Friday), the Thursday before is inadequate:
    # - Wed/Thursday trips: That's a full *week* too soon!
    # - Friday trips: 24 hours is not enough time.
    open_dt = (trip_date - timedelta(days=2)) if trip_dow in (2, 3, 4) else thur_before

    return localize(datetime.combine(open_dt, time(hour=18, minute=0)))


def late_at_night(dt: date) -> datetime:
    """23:59 on the date, since midnight is technically the next day."""
    # Note that this function *could* work with a `datetime` object.
    # However, timezones can make date identification tricky.
    # This method just means to give "shy of midnight" in Eastern time, on the date.
    # If `dt` were a datetime representing 2 am in England, what's the date?
    # Depends if you're asking from the perspective of those in England, or New England
    return localize(datetime(dt.year, dt.month, dt.day, 23, 59, 59))  # noqa: DTZ001


def fcfs_close_time(trip_date: date) -> datetime:
    """The time that a WS trip should close its first-come, first-serve signups.

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


def local_now() -> datetime:
    return timezone.localtime(timezone.now())


def local_now_to_the_minute() -> datetime:
    """Present time, rounded down to have zero seconds.

    (This is a function only because Django can't serialize lambdas for a `default`).
    """
    return local_now().replace(second=0, microsecond=0)


def local_date() -> date:
    return local_now().date()


def nearest_sat() -> date:
    """Give the date of the nearest Saturday (next week if today is Saturday)

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


def lottery_time(lottery_date: datetime) -> datetime:
    """Given a date, return the datetime when lottery trips should close.

    If changing the lottery time, modify just this method (others depend on it).
    """
    return lottery_date.replace(hour=9, minute=0, second=0, microsecond=0)


def next_lottery() -> datetime:
    lottery_morning = wed_morning()  # Closest Wednesday, at 9 am
    if local_now() > lottery_morning:  # Today is Wednesday, after lottery
        return lottery_time(lottery_morning + timedelta(days=7))
    return lottery_morning


def next_wednesday() -> datetime:
    now = local_now()
    days_til_wed = timedelta((9 - now.weekday()) % 7)
    return now + days_til_wed


def wed_morning() -> datetime:
    return lottery_time(next_wednesday())


def closest_wednesday() -> date:
    now = local_now()
    next_wed = next_wednesday()
    last_wed = next_wed - timedelta(7)
    return min([next_wed, last_wed], key=lambda dt: abs(now - dt)).date()


def closest_wed_at_noon() -> datetime:
    """Useful in case lottery is run slightly after noon on Wednesday."""
    closest_wed = closest_wednesday()
    ret = datetime.combine(closest_wed, datetime.min.time().replace(hour=12))
    return localize(ret)


def is_currently_iap() -> bool:
    """Returns if it's currently MIT's "Independent Activities Period"

    Winter School takes place during IAP each year. This (extremely approximate!) method
    is used to infer if it's roughly the time of year that Winter School takes place. We
    use it to give warnings about lottery preferences or other things that only make
    sense during IAP.

    This should likely be combined with `ws_lectures_complete` or other means of
    inspecting presence of trips. Combined, (that will give a more authoritative picture
    of whether or not Winter School is actually ongoing.
    """
    # Warning: This is only approximate! We cannot define when IAP occurs each year
    now = local_now()
    return now.month == 1 or (now.month == 2 and now.day < 7)


def ws_year() -> int:
    """Returns the year of the nearest Winter School."""
    this_year = local_now().year
    return this_year if local_now().month <= 6 else this_year + 1


def jan_1() -> datetime:
    jan_1st = datetime(local_date().year, 1, 1)  # noqa: DTZ001
    return localize(jan_1st)


def default_signups_close_at() -> datetime:
    """Return the default for when signups should close.

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


def ws_lectures_complete() -> bool:
    """Return if the mandatory first two lectures have occurred.

    Because IAP varies every year, use traits of the first week of Winter
    School in order to determine if lectures have completed.

    If there are completed Winter School trips this year, then it's no longer
    the first week, and lectures have completed. If it's at least Thursday
    night and there are future trips, we can deduce that lectures have ended.
    """
    # Avoid hitting the database if we don't need to.
    # The first week of Winter School always, always, is in early January.
    if not is_currently_iap():
        return False

    now = local_now()
    today = now.date()

    trips_this_ws = models.Trip.objects.filter(
        trip_date__gte=jan_1(),
        program=enums.Program.WINTER_SCHOOL.value,
    )

    dow = now.weekday()
    after_thursday = dow > 3 or dow == 3 and now.hour >= 21

    if trips_this_ws.filter(trip_date__lt=today):
        return True
    if trips_this_ws.filter(trip_date__gte=today) and after_thursday:
        return True
    # It's Winter School, but it's not late enough in the first week
    return False
