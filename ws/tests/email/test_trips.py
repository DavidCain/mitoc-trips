from datetime import date, datetime, time, timedelta

from django.core import mail
from freezegun import freeze_time

from ws.email.trips import send_trips_summary
from ws.tests import TestCase, factories
from ws.utils.dates import localize


class TripsBlastTest(TestCase):
    def setUp(self):
        super().setUp()
        self.presi = self._create_trip(
            trip_date=date(2020, 1, 2),
            name="Presi Traverse",
            difficulty_rating="Very hard",
            maximum_participants=4,
            algorithm='fcfs',
        )
        self.frankie = self._create_trip(
            trip_date=date(2020, 1, 8),
            name="Frankenstein Ice Climbing",
            difficulty_rating="cold",
        )

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

    @freeze_time("Wed, 15 Jan 2020 14:45:00 EST")
    def test_no_email_sent(self):
        """ When there are no current or upcoming trips, no email is sent. """
        send_trips_summary()
        self.assertFalse(mail.outbox)

    @freeze_time("Wed, 1 Jan 2020 12:25:00 EST")
    def test_no_future_trips(self):
        """ We only mention current trips if there are no future trips. """
        send_trips_summary()
        [msg] = mail.outbox

        # No future trips yet!
        expected_content = '\n'.join(
            [
                'This is a weekly digest of upcoming trips hosted by the MIT Outing Club.',
                'To unsubscribe, visit http://mailman.mit.edu/mailman/listinfo/mitoc-trip-announce',
                '---------------------------------------------------------------------------------',
                '',
                'Presi Traverse',
                '==============',
                f'<https://mitoc-trips.mit.edu/trips/{self.presi.pk}/>',
                'Thursday, January 2',
                'Difficulty rating: Very hard',
                'Spaces remaining: 4',
                'Signups close at: Jan. 1, 2020, 9:30 p.m.',
                'Algorithm: first-come, first-serve',
                '',
                'Frankenstein Ice Climbing',
                '=========================',
                f'<https://mitoc-trips.mit.edu/trips/{self.frankie.pk}/>',
                'Wednesday, January 8',
                'Difficulty rating: cold',
                'Spaces remaining: 8',
                'Signups close at: Jan. 7, 2020, 9:30 p.m.',
                'Algorithm: lottery',
                '',
                '',
                '',
                'Unsubscribe: http://mailman.mit.edu/mailman/options/mitoc-trip-announce',
            ]
        )
        self.assertEqual(msg.body, expected_content)

    @freeze_time("Wed, 1 Jan 2020 12:25:00 EST")
    def test_upcoming_trips(self):
        """ We break trips into those that are open now, and those open in the future. """
        future = self._create_trip(
            trip_date=date(2021, 11, 21),
            name="Future trip",
            difficulty_rating="N/A",
            maximum_participants=20,
            algorithm='lottery',
        )

        send_trips_summary()
        [msg] = mail.outbox

        # The trip next week is open for signup
        # The future trips are not yet open for signup
        expected_content = '\n'.join(
            [
                'This is a weekly digest of upcoming trips hosted by the MIT Outing Club.',
                'To unsubscribe, visit http://mailman.mit.edu/mailman/listinfo/mitoc-trip-announce',
                '---------------------------------------------------------------------------------',
                '',
                'Presi Traverse',
                '==============',
                f'<https://mitoc-trips.mit.edu/trips/{self.presi.pk}/>',
                'Thursday, January 2',
                'Difficulty rating: Very hard',
                'Spaces remaining: 4',
                'Signups close at: Jan. 1, 2020, 9:30 p.m.',
                'Algorithm: first-come, first-serve',
                '',
                'Frankenstein Ice Climbing',
                '=========================',
                f'<https://mitoc-trips.mit.edu/trips/{self.frankie.pk}/>',
                'Wednesday, January 8',
                'Difficulty rating: cold',
                'Spaces remaining: 8',
                'Signups close at: Jan. 7, 2020, 9:30 p.m.',
                'Algorithm: lottery',
                '',
                '',
                '',
                'Upcoming trips (not yet open)',
                '-----------------------------',
                '',
                'Future trip',
                '===========',
                f'<https://mitoc-trips.mit.edu/trips/{future.pk}/>',
                'Sunday, November 21',
                'Difficulty rating: N/A',
                'Signups open at: Nov. 14, 2021, noon',
                'Algorithm: lottery',
                '',
                '',
                'Unsubscribe: http://mailman.mit.edu/mailman/options/mitoc-trip-announce',
            ]
        )
        self.assertEqual(msg.body, expected_content)
