from datetime import date, datetime, time, timedelta

from django.template import Context, Template
from django.template.loader import get_template
from freezegun import freeze_time

from ws.email.trips import send_trips_summary, trips_to_summarize
from ws.tests import TestCase, factories
from ws.utils.dates import local_now, localize


class TripsBlastTest(TestCase):
    @staticmethod
    def _create_trip(**kwargs):
        """ Create a trip with signups opening one week before, closing night before. """
        trip_date = kwargs.pop('trip_date')
        open_date = trip_date - timedelta(days=7)
        day_before = trip_date - timedelta(days=1)

        return factories.TripFactory.create(
            trip_date=trip_date,
            signups_open_at=localize(datetime.combine(open_date, time(12, 0))),
            signups_close_at=localize(datetime.combine(day_before, time(21, 30))),
            **kwargs,
        )

    @staticmethod
    def _upcoming_trip_summary(trip):
        context = Context({'trip': trip})
        txt_template = Template(
            '{% load email_tags %}{% upcoming_trip_summary_txt trip %}'
        )
        return txt_template.render(context)

    def test_no_email_sent(self):
        """ When there are no upcoming trips, no email is sent. """
        message = send_trips_summary()
        self.assertIsNone(message)

    def test_past_trips_ignored(self):
        """ We only report upcoming trips. """
        yesterday = local_now().date() - timedelta(days=1)
        factories.TripFactory.create(trip_date=yesterday)
        message = send_trips_summary()
        self.assertIsNone(message)

    @freeze_time("Wed, 1 Jan 2020 12:25:00 EST")
    def test_trips_to_summarize(self):
        """ We break trips into those that are open now, and those open in the future. """
        next_week = self._create_trip(trip_date=date(2020, 1, 8))
        next_month = self._create_trip(trip_date=date(2020, 2, 12))
        next_year = self._create_trip(trip_date=date(2021, 11, 21))

        self.assertTrue(next_week.signups_open)
        self.assertTrue(next_month.signups_not_yet_open)
        self.assertTrue(next_year.signups_not_yet_open)

        open_for_signup, not_yet_open = trips_to_summarize()

        # The trip next week is open for signup
        self.assertEqual(open_for_signup, [next_week])
        next_week = open_for_signup[0]  # Get annotations on this trip!

        # The future trips are not yet open for signup
        self.assertEqual(not_yet_open, [next_month, next_year])

        context = {'open_for_signup': open_for_signup, 'not_yet_open': not_yet_open}
        text_content = get_template('email/trips/upcoming_trips.txt').render(context)
        expected_content = '\n'.join(
            [
                '',
                'This is a weekly digest of upcoming trips hosted by the MIT Outing Club.',
                'To unsubscribe, visit http://mailman.mit.edu/mailman/listinfo/mitoc-trip-announce',
                '---------------------------------------------------------------------------------',
                '',
                self._upcoming_trip_summary(next_week),
                '',
                '',
                'Upcoming trips (not yet open)',
                '-----------------------------',
                '',
                self._upcoming_trip_summary(next_month),
                '',
                self._upcoming_trip_summary(next_year),
                '',
                'Unsubscribe: http://mailman.mit.edu/mailman/options/mitoc-trip-announce',
                '',
            ]
        )
        self.assertEqual(text_content, expected_content)

    @freeze_time("Wed, 1 Jan 2020 12:25:00 EST")
    def test_no_upcoming_trips(self):
        """ We only mention current trips if there are no future trips. """
        tomorrow = self._create_trip(trip_date=date(2020, 1, 2))
        next_week = self._create_trip(trip_date=date(2020, 1, 8))

        open_for_signup, not_yet_open = trips_to_summarize()
        self.assertEqual(open_for_signup, [tomorrow, next_week])
        # pylint: disable=unbalanced-tuple-unpacking
        tomorrow, next_week = open_for_signup  # Get annotated models!

        # No future trips yet
        self.assertEqual(not_yet_open, [])

        context = {'open_for_signup': open_for_signup, 'not_yet_open': not_yet_open}
        text_content = get_template('email/trips/upcoming_trips.txt').render(context)
        expected_content = '\n'.join(
            [
                '',
                'This is a weekly digest of upcoming trips hosted by the MIT Outing Club.',
                'To unsubscribe, visit http://mailman.mit.edu/mailman/listinfo/mitoc-trip-announce',
                '---------------------------------------------------------------------------------',
                '',
                self._upcoming_trip_summary(tomorrow),
                self._upcoming_trip_summary(next_week),
                '',
                '',
                'Unsubscribe: http://mailman.mit.edu/mailman/options/mitoc-trip-announce',
                '',
            ]
        )
        self.assertEqual(text_content, expected_content)
