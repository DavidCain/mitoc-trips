from datetime import date
from unittest import mock

from bs4 import BeautifulSoup
from django.core import mail

from ws import models
from ws.email import sole
from ws.tests import TestCase, factories


class StudentTravelFormTest(TestCase):
    def setUp(self):
        super().setUp()
        self.leader = factories.ParticipantFactory.create(
            name="Tim Beaver", email="tim@mit.edu", cell_phone="+6172531000"
        )
        self.trip = factories.TripFactory.create(
            name="Mt. Lafayette",
            trip_date=date(2019, 10, 12),
            info=factories.TripInfoFactory.create(
                start_location='Old Bridle Path trailhead'
            ),
        )
        self.trip.leaders.add(self.leader)

        suzy = factories.ParticipantFactory(
            name="Suzy Queue", email="suzy@example.com", cell_phone="+17815551234"
        )
        self.joe = factories.ParticipantFactory(
            name="Joe Schmo", email="joe@example.com", cell_phone=""
        )
        factories.SignUpFactory.create(participant=suzy, trip=self.trip, on_trip=True)
        factories.SignUpFactory.create(
            participant=self.joe, trip=self.trip, on_trip=True
        )

        # Participants on the waiting list or otherwise not on the trip aren't considered
        factories.SignUpFactory.create(trip=self.trip, on_trip=False)
        on_waitlist = factories.SignUpFactory.create(trip=self.trip, on_trip=False)
        factories.WaitListSignupFactory.create(signup=on_waitlist)

    def _expect_plaintext_contents(self, msg):
        """The plaintext email contains basically the same contents as the HTML."""
        self.assertTrue(
            msg.body.startswith(
                '\nThis automated message is registering an official trip of the MIT Outing Club (MITOC)'
            )
        )
        self.assertIn('Date: 2019-10-12', msg.body)
        self.assertIn('Start location: Old Bridle Path trailhead', msg.body)

        self.assertIn('Trip leaders:\n  - Tim Beaver (tim@mit.edu)', msg.body)
        on_trip = '\n'.join(
            [
                'Trip participants:',
                '  - Suzy Queue (suzy@example.com) +17815551234',
                '  - Joe Schmo (joe@example.com)',
            ]
        )
        self.assertIn(on_trip, msg.body)

        self.assertIn('Cost object: 2720209', msg.body)

    def _dl_elements(self, dl):
        self.assertEqual(dl.name, 'dl')
        for dt in dl.find_all('dt'):
            dd = dt.find_next_sibling()
            self.assertEqual(dd.name, 'dd')
            yield dt.get_text(), dd.get_text()

    def _expect_html_contents(self, msg):
        self.assertEqual(msg.alternatives, [(mock.ANY, 'text/html')])
        soup = BeautifulSoup(msg.alternatives[0][0], 'html.parser')

        self.assertEqual(
            soup.find('p').get_text(' ', strip=True),
            'This automated message is registering an official trip of the MIT Outing Club (MITOC).',
        )

        info = soup.find('h3', string='Mt. Lafayette').find_next_sibling('dl')
        self.assertEqual(
            dict(self._dl_elements(info)),
            {'Date': '2019-10-12', 'Start location': 'Old Bridle Path trailhead'},
        )

        # Trip leaders are enumerated, with contact info
        leaders = (
            soup.find('h3', string='Trip leaders')
            .find_next_sibling('ul')
            .find_all('li')
        )
        self.assertEqual(len(leaders), 1)
        self.assertEqual(leaders[0].get_text(' ', strip=True), 'Tim Beaver')
        self.assertEqual(leaders[0].find('a')['href'], 'mailto:tim@mit.edu')

        # We list trip participants
        participants = (
            soup.find('h3', string='Trip participants')
            .find_next_sibling('ul')
            .find_all('li')
        )
        suzy, joe = participants
        self.assertEqual(suzy.find('a').text, 'Suzy Queue')
        self.assertEqual(suzy.find('a')['href'], 'mailto:suzy@example.com')
        self.assertEqual(joe.get_text(' ', strip=True), 'Joe Schmo')
        self.assertEqual(joe.find('a')['href'], 'mailto:joe@example.com')

        # Suzy has a cell phone, Joe does not
        self.assertEqual(suzy.find('em').text, '+17815551234')
        self.assertIsNone(joe.find('em'))

        # Signatory info
        approval = soup.find('h3', string='Approval').find_next_sibling('dl')
        self.assertEqual(
            dict(self._dl_elements(approval)),
            {
                'Financial signatory': 'MITOC Bursar',
                'Travel expenses approved': '$0.00',
                'Cost object': '2720209',
            },
        )

        # Driver info is given (contents tested separately)
        self.assertIsNotNone(soup.find('h3', string='Drivers'))
        return soup

    def _expect_basics(self, msg):
        self.assertEqual(msg.subject, 'MITOC-Trips registration: Mt. Lafayette')
        self.assertEqual(msg.from_email, 'mitoc-trips@mit.edu')
        self.assertEqual(msg.to, ['sole-desk@mit.edu'])
        self.assertEqual(msg.cc, ['mitoc-bursar@mit.edu'])
        self.assertEqual(msg.reply_to, ['mitoc-bursar@mit.edu'])

    def test_message(self):
        sole.send_email_to_funds(self.trip)

        # Results in sending a single email
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]

        self._expect_basics(msg)
        self._expect_plaintext_contents(msg)
        soup = self._expect_html_contents(msg)

        # no drivers in this test!
        self.assertEqual(
            soup.find('h3', string='Drivers')
            .find_next_sibling('p')
            .get_text(' ', strip=True),
            'Nobody on this trip submitted information for a car.',
        )
        self.assertIn(
            'Drivers:\n  Nobody on this trip submitted information for a car.\n',
            msg.body,
        )

    def test_has_drivers(self):
        """Both leaders and participants will be reported as drivers."""
        self.leader.car = factories.CarFactory(
            make='Toyota',
            model='Prius',
            license_plate='VANITY',
            state='NH',
            year='2019',
            color='Blue',
        )
        self.leader.save()
        with self.assertRaises(models.LotteryInfo.DoesNotExist):
            self.leader.lotteryinfo  # pylint: disable=pointless-statement

        self.trip.info.drivers.add(self.leader)

        self.joe.car = factories.CarFactory.create(
            make='Ford',
            model='Fiesta',
            license_plate='ABC 123',
            state='VT',
            year='2001',
            color='Green',
        )
        self.joe.save()
        factories.LotteryInfoFactory.create(participant=self.joe, car_status="own")

        self.trip.info.drivers.add(self.joe)

        sole.send_email_to_funds(self.trip)

        # Results in sending a single email
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]

        self._expect_basics(msg)
        self._expect_plaintext_contents(msg)
        soup = self._expect_html_contents(msg)

        # Make sure that both participant and leader drivers are given in the table!
        drivers_table = soup.find('h3', string='Drivers').find_next_sibling('table')
        header = [el.text for el in drivers_table.find('thead').find_all('th')]
        rows = drivers_table.find('tbody').find_all('tr')
        drivers = [zip(header, (td.text for td in row.find_all('td'))) for row in rows]
        expected = [
            [
                ('Driver', 'Tim Beaver'),
                ('Make + Model', 'Toyota Prius'),
                ('Plate', 'VANITY'),
                ('State', 'NH'),
                ('Year', '2019'),
                ('Color', 'Blue'),
                # The leader never submitted lottery info
                ('Car Status', ''),
            ],
            [
                ('Driver', 'Joe Schmo'),
                ('Make + Model', 'Ford Fiesta'),
                ('Plate', 'ABC 123'),
                ('State', 'VT'),
                ('Year', '2001'),
                ('Color', 'Green'),
                ('Car Status', 'Can drive own car'),
            ],
        ]
        self.assertCountEqual([list(driver) for driver in drivers], expected)

        as_text = '\n'.join(
            [
                'Drivers:',
                ' - Tim Beaver: Blue 2019 Toyota Prius VANITY (NH)',
                ' - Joe Schmo: Green 2001 Ford Fiesta ABC 123 (VT)',
                '\n',
            ]
        )
        self.assertIn(as_text, msg.body)
