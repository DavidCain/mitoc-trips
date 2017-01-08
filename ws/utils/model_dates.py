"""
Dateutils that require using models.

This is a separate module to avoid creating circular dependencies.
"""
from ws import models

import ws.utils.dates as dateutils


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
    jan_1 = dateutils.jan_1()
    trips_this_ws = models.Trip.objects.filter(trip_date__gte=jan_1, activity='winter_school')

    after_thursday = now.day > 5 or now.day == 5 and now.hour >= 21

    if trips_this_ws.filter(trip_date__lt=today):
        return True
    elif trips_this_ws.filter(trip_date__gte=today) and after_thursday:
        return True
    else:  # It's Winter School, but it's not late enough in the first week
        return False


def missed_lectures(participant, year):
    """ Whether the participant missed WS lectures in the given year. """
    if year < 2016:  # We lack records for 2014 & 2015; assume present
        return False
    absent = not participant.lectureattendance_set.filter(year=year).exists()

    # If this year's lectures haven't happened yet, don't consider to have missed
    if year == dateutils.ws_year():
        return ws_lectures_complete() and absent
    else:
        return absent
