from datetime import datetime, timedelta
import mock
from unittest import TestCase  # Don't need database

from ws.utils import dates as date_utils


class DateUtilTests(TestCase):
    """ Test the date utilities that lots of lottery logic depends on.

    These methods don't depend on models and don't expect any particular
    timezone, so we can test them in UTC.
    """
    fixtures = ['ws']

    def setUp(self):
        self.y2k = datetime(2000, 1, 1)
        self.test_datetimes = [self.y2k + timedelta(days=i) for i in range(15)]

    def test_friday_before(self):
        for test_dt in self.test_datetimes:
            fri_before = date_utils.friday_before(test_dt)
            self.assertEqual(fri_before.weekday(), 4)  # Is always a Friday

            if test_dt.weekday() == 4:
                self.assertEqual(test_dt, fri_before)
            else:
                self.assertGreater(test_dt, fri_before)

    @mock.patch('ws.utils.dates.local_now')
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

    @mock.patch('ws.utils.dates.local_now')
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

    @mock.patch('ws.utils.dates.local_now')
    def test_is_winter_school(self, local_now):
        for day, expected in [(datetime(2016,12,28), False),
                              (datetime(2017, 1, 1), True),
                              (datetime(2017, 1,14), True),
                              (datetime(2017, 1,31), True),
                              (datetime(2017, 2,10), False)]:
            local_now.return_value = day
            self.assertEqual(date_utils.is_winter_school(), expected)
