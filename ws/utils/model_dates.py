"""
Dateutils that require using models.

This is a separate module to avoid creating circular dependencies.
"""
import ws.utils.dates as dateutils
from ws import models


def _ws_trips_this_year():
    jan_1 = dateutils.jan_1()
    return models.Trip.objects.filter(trip_date__gte=jan_1, activity='winter_school')


def ws_lectures_complete():
    """ Return if the mandatory first two lectures have occurred.

    Because IAP varies every year, use traits of the first week of Winter
    School in order to determine if lectures have completed.

    If there are completed Winter School trips this year, then it's no longer
    the first week, and lectures have completed. If it's at least Thursday
    night and there are future trips, we can deduce that lectures have ended.
    """
    now = dateutils.local_now()
    today = now.date()
    trips_this_ws = _ws_trips_this_year()

    dow = now.weekday()
    after_thursday = dow > 3 or dow == 3 and now.hour >= 21

    if trips_this_ws.filter(trip_date__lt=today):
        return True
    if trips_this_ws.filter(trip_date__gte=today) and after_thursday:
        return True
    # It's Winter School, but it's not late enough in the first week
    return False


def missed_lectures(participant, year):
    """ Whether the participant missed WS lectures in the given year. """
    if year < 2016:
        return False  # We lack records for 2014 & 2015; assume present
    if year == dateutils.ws_year() and not ws_lectures_complete():
        return False  # Lectures aren't over yet, so nobody "missed" lectures

    return not participant.lectureattendance_set.filter(year=year).exists()
