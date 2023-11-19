from datetime import date, datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from freezegun import freeze_time

from ws import enums
from ws.tests import factories
from ws.utils import dates as date_utils


class ItineraryAvailableAtTest(TestCase):
    """Test the date utilities that lots of lottery logic depends on.

    These methods don't depend on models and don't expect any particular
    timezone, so we can test them in UTC.
    """

    eastern = ZoneInfo("America/New_York")

    def test_sensible_range(self):
        """We always allow at least 1 full day to submit, but never allow more than 5."""
        for day_of_month in range(1, 31):
            trip_date = date(2022, 1, day_of_month)
            opens_at = date_utils.itinerary_available_at(trip_date)

            self.assertEqual(opens_at.time().isoformat(), "18:00:00")

            self.assertLess(opens_at.date(), trip_date)

            days_lead_time = trip_date - opens_at.date()
            self.assertGreater(days_lead_time, timedelta(days=1))
            self.assertLess(days_lead_time, timedelta(days=6))

    def test_weekend_trips(self):
        """Trips on Saturday or Sunday have open itineraries on Thursday evening.

        This enables ample lead time for the usual Winter School setup (where
        there are no holidays on a Friday).
        """
        self.assertEqual(
            date_utils.itinerary_available_at(date(2022, 1, 15)),
            datetime(2022, 1, 13, 18, 0, 0, tzinfo=self.eastern),
        )

        self.assertEqual(
            date_utils.itinerary_available_at(date(2022, 1, 16)),
            datetime(2022, 1, 13, 18, 0, 0, tzinfo=self.eastern),
        )

    def test_mlk_day(self):
        """Monday trips *might* be on a holiday weekend, so we allow Thursday submission.

        It's important we allow submission *before* the weekend,
        to accommodate leaders who may be going out on all three days.
        """
        self.assertEqual(
            date_utils.itinerary_available_at(date(2022, 1, 17)),
            datetime(2022, 1, 13, 18, 0, 0, tzinfo=self.eastern),
        )

    def test_wed_trips(self):
        """Wednesday trips open on Monday night, even if Monday is a holiday."""
        # All trips on Wednesday nights open on Monday night.
        self.assertEqual(
            date_utils.itinerary_available_at(date(2022, 7, 13)),
            datetime(2022, 7, 11, 18, 0, 0, tzinfo=self.eastern),
        )

        # January 17th is MLK day (3-day weekend in WS). Consider a trip that Wednesday.
        # If leaders are on a trip that day, we assume they'll be home to submit on Monday night.
        # (Or ideally, that they can submit some time on Tuesday)
        # Allowing itinerary submission Thursday before the long weekend is just too much time.
        self.assertEqual(
            date_utils.itinerary_available_at(date(2022, 1, 19)),
            datetime(2022, 1, 17, 18, 0, 0, tzinfo=self.eastern),
        )

    def test_thursday_and_friday_trips(self):
        """Trips on Thursday & Friday open two days before the trip date."""
        self.assertEqual(
            date_utils.itinerary_available_at(date(2022, 7, 14)),
            datetime(2022, 7, 12, 18, 0, 0, tzinfo=self.eastern),
        )
        self.assertEqual(
            date_utils.itinerary_available_at(date(2022, 7, 15)),
            datetime(2022, 7, 13, 18, 0, 0, tzinfo=self.eastern),
        )


class DateUtilTests(TestCase):
    def setUp(self):
        self.y2k = datetime(2000, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        self.test_datetimes = [self.y2k + timedelta(days=i) for i in range(15)]

    @mock.patch("ws.utils.dates.local_now")
    def test_nearest_sat(self, local_now):
        for test_dt in self.test_datetimes:
            local_now.return_value = test_dt
            nearest_sat = date_utils.nearest_sat()
            self.assertEqual(nearest_sat.weekday(), 5)  # Always a Saturday

            test_date = test_dt.date()
            if test_date.weekday() == 5:  # Today's a Saturday, will pick next one
                self.assertEqual(nearest_sat - test_date, timedelta(days=7))
            else:
                self.assertGreater(nearest_sat, test_date)

    @mock.patch("ws.utils.dates.local_now")
    def test_closest_wednesday(self, local_now):
        for test_dt in self.test_datetimes:
            local_now.return_value = test_dt
            closest_wed = date_utils.closest_wednesday()
            self.assertEqual(closest_wed.weekday(), 2)

            test_date = test_dt.date()
            if test_date.weekday() == 2:
                self.assertEqual(test_date, closest_wed)
            elif 3 <= test_date.weekday() <= 5:  # Thursday -> Saturday
                self.assertGreater(test_date, closest_wed)
            else:
                self.assertLess(test_date, closest_wed)

    def test_closest_wed_at_noon(self):
        eastern = ZoneInfo("America/New_York")

        # On Wednesday, we return the same day
        with freeze_time("2016-12-28 23:22 EST"):
            self.assertEqual(
                date_utils.closest_wed_at_noon(),
                datetime(2016, 12, 28, 12, 0, 0, tzinfo=eastern),
            )

        # 3 days to the next Wednesday, 4 days to the previous
        with freeze_time("2016-12-25 10:00 EST"):
            self.assertEqual(
                date_utils.closest_wed_at_noon(),
                datetime(2016, 12, 28, 12, 0, 0, tzinfo=eastern),
            )

        # 4 days to the next Wednesday, 3 days to the previous
        with freeze_time("2016-12-24 10:00 EST"):
            self.assertEqual(
                date_utils.closest_wed_at_noon(),
                datetime(2016, 12, 21, 12, 0, 0, tzinfo=eastern),
            )

    def test_is_currently_iap(self):
        """Test the method that approximates if it's Winter School."""
        # December before Winter School
        with freeze_time("2016-12-28 12:00 EST"):
            self.assertFalse(date_utils.is_currently_iap())

        # Weeks during Winter School
        with freeze_time("2017-01-01 12:00 EST"):
            self.assertTrue(date_utils.is_currently_iap())
        with freeze_time("2017-01-14 12:00 EST"):
            self.assertTrue(date_utils.is_currently_iap())
        with freeze_time("2017-01-31 12:00 EST"):
            self.assertTrue(date_utils.is_currently_iap())

        # The week after Winter School is over
        with freeze_time("2017-02-10 12:00 EST"):
            self.assertFalse(date_utils.is_currently_iap())

    def test_fcfs_close_time(self):
        eastern = ZoneInfo("America/New_York")
        thur_night = datetime(2019, 1, 24, 23, 59, 59, tzinfo=eastern)

        # For the usual case (trips over the weekend), it's the Thursday beforehand
        (fri, sat, sun, mon) = (date(2019, 1, dom) for dom in [25, 26, 27, 28])
        self.assertEqual(date_utils.fcfs_close_time(fri), thur_night)
        self.assertEqual(date_utils.fcfs_close_time(sat), thur_night)
        self.assertEqual(date_utils.fcfs_close_time(sun), thur_night)
        self.assertEqual(date_utils.fcfs_close_time(mon), thur_night)

        # Tuesday & Wednesday trips shouldn't really happen as part of the normal lottery
        # That said, if they *are* part of the lottery, they were posted 1 week in advance.
        tue, wed = date(2019, 1, 29), date(2019, 1, 30)
        self.assertEqual(date_utils.fcfs_close_time(tue), thur_night)
        self.assertEqual(date_utils.fcfs_close_time(wed), thur_night)

        # A trip taking place on Thursday should close the night before
        # (otherwise, it would be closing *after* the trip completes!
        wed_night = thur_night - timedelta(days=1)
        self.assertEqual(date_utils.fcfs_close_time(date(2019, 1, 24)), wed_night)

    def test_next_lottery(self):
        eastern = ZoneInfo("America/New_York")
        friday_the_23rd = datetime(2019, 1, 23, 9, 0, 0, tzinfo=eastern)
        friday_the_30th = datetime(2019, 1, 30, 9, 0, 0, tzinfo=eastern)

        # Normal cases: lottery is always just the next Wednesday morning
        with freeze_time("Fri, 25 Jan 2019 03:00:00 EST"):
            self.assertEqual(date_utils.next_lottery(), friday_the_30th)
        with freeze_time("Mon, 28 Jan 2019 12:42:37 EST"):
            self.assertEqual(date_utils.next_lottery(), friday_the_30th)

        # Before the scheduled lottery time, it's in a few minutes!
        with freeze_time("Wed, 23 Jan 2019 08:52:34 EST"):
            self.assertEqual(date_utils.next_lottery(), friday_the_23rd)

        # After the scheduled lottery time: it's next week
        with freeze_time("Wed, 23 Jan 2019 09:05:00 EST"):
            self.assertEqual(date_utils.next_lottery(), friday_the_30th)


class LecturesCompleteTests(TestCase):
    """Test the method that tries to infer when lectures are over."""

    @staticmethod
    def _create_ws_trip(trip_date, **kwargs):
        factories.TripFactory.create(
            trip_date=trip_date, program=enums.Program.WINTER_SCHOOL.value, **kwargs
        )

    @freeze_time("Wednesday, Jan 3 2018 15:00:00 EST")
    def test_no_trips_yet(self):
        """When there are no trips this Winter School, lectures aren't complete.

        (The first trips are posted on Thursday of the first lecture week - without
        these trips, we can reasonably infer that lectures are still ongoing)
        """
        # Create trips from previous Winter School
        self._create_ws_trip(date(2017, 1, 15))
        self._create_ws_trip(date(2017, 1, 28))

        self.assertFalse(date_utils.ws_lectures_complete())

    @freeze_time("Friday, Jan 13 2017 12:34:00 EST")
    def test_past_trips(self):
        """When trips have already completed, lectures are definitely over."""
        self._create_ws_trip(date(2017, 1, 12))
        self.assertTrue(date_utils.ws_lectures_complete())

    def test_future_trips(self):
        """When there are no past trips, but there are upcoming trips."""

        self._create_ws_trip(date(2018, 1, 5))
        self._create_ws_trip(date(2018, 1, 6))

        # Test calling this function at various times of day
        expectations = {
            # There are future trips, but it's not yet Thursday night
            # (Explanation: Some leaders got ansty and created trips early)
            "Wed 2018-01-03 12:00 EST": False,
            # It's evening, but lectures have just started
            "Thu 2018-01-04 19:00 EST": False,
            # Leaders created trips, and it's after 9 pm, so we infer lectures are over
            "Thu 2018-01-04 21:15 EST": True,
            # It's Friday, with upcoming trips. Lectures are definitely over.
            "Fri 2018-01-05 10:23 EST": True,
        }

        for time_string, lectures_over in expectations.items():
            with freeze_time(time_string):
                self.assertEqual(date_utils.ws_lectures_complete(), lectures_over)
