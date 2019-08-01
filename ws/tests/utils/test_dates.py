import unittest.mock
from datetime import date, datetime, timedelta

from django.test import SimpleTestCase  # No need for database

from ws.utils import dates as date_utils


class DateFromIsoTests(unittest.TestCase):
    def test_raises_type_error(self):
        with self.assertRaises(TypeError):
            date_utils.date_from_iso(None)
        with self.assertRaises(TypeError):
            date_utils.date_from_iso(37)

    def test_raises_value_error(self):
        with self.assertRaises(ValueError):
            date_utils.date_from_iso('2019-06-99')

    def test_succesfully_parses(self):
        parsed_date = date_utils.date_from_iso('2019-06-19')
        self.assertEqual(parsed_date, date(2019, 6, 19))


class DateUtilTests(SimpleTestCase):
    """ Test the date utilities that lots of lottery logic depends on.

    These methods don't depend on models and don't expect any particular
    timezone, so we can test them in UTC.
    """

    def setUp(self):
        self.y2k = datetime(2000, 1, 1)
        test_datetimes = [self.y2k + timedelta(days=i) for i in range(15)]
        self.test_datetimes = [date_utils.localize(dt) for dt in test_datetimes]

    def test_itinerary_available_at(self):
        for test_dt in self.test_datetimes:
            avail_datetime = date_utils.itinerary_available_at(test_dt)
            self.assertEqual(avail_datetime.weekday(), 3)  # Is always a Thursday

            if test_dt.weekday() == 3:
                self.assertEqual(test_dt.date(), avail_datetime.date())
            else:
                self.assertGreater(test_dt, avail_datetime)

    @unittest.mock.patch('ws.utils.dates.local_now')
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

    @unittest.mock.patch('ws.utils.dates.local_now')
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
        wed_noon = date_utils.closest_wed_at_noon()
        self.assertEqual(wed_noon.hour, 12)
        self.assertEqual(wed_noon.minute, 0)

    @unittest.mock.patch('ws.utils.dates.local_now')
    def test_is_winter_school(self, local_now):
        for day, expected in [
            (datetime(2016, 12, 28), False),
            (datetime(2017, 1, 1), True),
            (datetime(2017, 1, 14), True),
            (datetime(2017, 1, 31), True),
            (datetime(2017, 2, 10), False),
        ]:
            local_now.return_value = day
            self.assertEqual(date_utils.is_winter_school(), expected)
