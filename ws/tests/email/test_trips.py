from datetime import date, datetime, time, timedelta

from bs4 import BeautifulSoup
from django.core import mail
from freezegun import freeze_time

from ws import enums
from ws.email.trips import send_trips_summary
from ws.tests import TestCase, factories, strip_whitespace
from ws.utils.dates import localize


class TripsBlastTest(TestCase):
    def setUp(self):
        super().setUp()
        self.presi = self._create_trip(
            trip_date=date(2020, 1, 2),
            program=enums.Program.WINTER_SCHOOL.value,
            trip_type=enums.TripType.HIKING.value,
            level="C",
            name="Presi Traverse",
            difficulty_rating="Very hard",
            prereqs="High level of fitness",
            maximum_participants=4,
            algorithm='fcfs',
        )
        self.presi.leaders.add(factories.ParticipantFactory.create(name="Tim Beaver"))
        self.presi.leaders.add(factories.ParticipantFactory.create(name="Jane Example"))

        self.frankie = self._create_trip(
            trip_date=date(2020, 1, 8),
            name="Frankenstein Ice Climbing",
            level="I A",
            difficulty_rating="cold",
            program=enums.Program.WINTER_SCHOOL.value,
            trip_type=enums.TripType.ICE_CLIMBING.value,
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
                'Program: Winter School -- Attendance at mandatory safety lectures is required: <https://mitoc.mit.edu/events/winter-school>',
                'Type: Hiking',
                'Level: C',
                'Difficulty rating: Very hard',
                'Leaders: Jane Example, Tim Beaver',
                'Prerequisites: High level of fitness',
                'Spaces remaining: 4',
                'Signups close at: Jan. 1, 2020, 9:30 p.m.',
                'Algorithm: first-come, first-serve',
                '',
                'Frankenstein Ice Climbing',
                '=========================',
                f'<https://mitoc-trips.mit.edu/trips/{self.frankie.pk}/>',
                'Wednesday, January 8',
                'Program: Winter School -- Attendance at mandatory safety lectures is required: <https://mitoc.mit.edu/events/winter-school>',
                'Type: Ice climbing',
                'Level: I A',
                'Difficulty rating: cold',
                'Spaces remaining: 8',
                'Signups close at: Jan. 7, 2020, 9:30 p.m.',
                'Algorithm: lottery',
                '',
                '',
                '',
                'Unsubscribe: http://mailman.mit.edu/mailman/listinfo/mitoc-trip-announce',
            ]
        )
        self.assertEqual(msg.body, expected_content)

    @freeze_time("Wed, 1 Jan 2020 12:25:00 EST")
    def test_upcoming_trips(self):
        """ We break trips into those that are open now, and those open in the future. """
        future = self._create_trip(
            trip_date=date(2021, 11, 21),
            name="Future trip",
            program=enums.Program.SERVICE.value,
            trip_type=enums.TripType.SPORT_CLIMBING.value,
            level=None,
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
                'Program: Winter School -- Attendance at mandatory safety lectures is required: <https://mitoc.mit.edu/events/winter-school>',
                'Type: Hiking',
                'Level: C',
                'Difficulty rating: Very hard',
                'Leaders: Jane Example, Tim Beaver',
                'Prerequisites: High level of fitness',
                'Spaces remaining: 4',
                'Signups close at: Jan. 1, 2020, 9:30 p.m.',
                'Algorithm: first-come, first-serve',
                '',
                'Frankenstein Ice Climbing',
                '=========================',
                f'<https://mitoc-trips.mit.edu/trips/{self.frankie.pk}/>',
                'Wednesday, January 8',
                'Program: Winter School -- Attendance at mandatory safety lectures is required: <https://mitoc.mit.edu/events/winter-school>',
                'Type: Ice climbing',
                'Level: I A',
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
                'Program: Service',
                'Type: Sport climbing, top rope',
                'Difficulty rating: N/A',
                'Signups open at: Nov. 14, 2021, noon',
                'Algorithm: lottery',
                '',
                '',
                'Unsubscribe: http://mailman.mit.edu/mailman/listinfo/mitoc-trip-announce',
            ]
        )
        self.assertEqual(msg.body, expected_content)

        # Check the HTML (which is chock full of email-specific CSS & structure)
        content = msg.alternatives[0][0]  # type: ignore
        soup = BeautifulSoup(content, 'html.parser')
        self.assertEqual(soup.title.text, 'Upcoming MITOC trips | Wednesday, January 1')
        self.assertIn(
            'http://mailman.mit.edu/mailman/listinfo/mitoc-trip-announce', soup.text
        )

        upcoming_trips = soup.find('h1', string='Trips currently open for signup')
        self.assertEqual(
            [
                heading.get_text(' ', strip=True)
                for heading in upcoming_trips.find_next_siblings('h2')
            ],
            # Note: `Future trip` will appear *after* the next h1
            ['Presi Traverse', 'Frankenstein Ice Climbing', 'Future trip'],
        )

        # Check formatting of one trip (others will be largely the same)
        presi = soup.find('h2').find_next_sibling('p')
        self.assertEqual(
            [strip_whitespace(li.text) for li in presi.find('ul').find_all('li')],
            [
                'Program: Winter School Attendance at mandatory safety lectures is required.',
                'Type: Hiking',
                'Level: C',
                'Difficulty rating: Very hard',
                'Leaders: Jane Example, Tim Beaver',
                'Prerequisites: High level of fitness',
                'Spaces remaining: 4',
                'Signups close at: Jan. 1, 2020, 9:30 p.m.',
                'Algorithm: first-come, first-serve',
            ],
        )

        future_trips = soup.find('h1', string='Upcoming trips (not yet open)')
        self.assertEqual(
            [
                heading.get_text(' ', strip=True)
                for heading in future_trips.find_next_siblings('h2')
            ],
            ['Future trip'],
        )
