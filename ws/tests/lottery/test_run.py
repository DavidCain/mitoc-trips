from datetime import date, datetime
from textwrap import dedent
from unittest.mock import patch

from freezegun import freeze_time
from mitoc_const import affiliations

import ws.utils.dates as date_utils
from ws import enums, models, settings
from ws.lottery import run
from ws.tests import TestCase, factories


class SingleTripLotteryTests(TestCase):
    def test_fcfs_not_run(self):
        """If a trip's algorithm is not 'lottery', nothing happens."""
        trip = factories.TripFactory.create(
            algorithm='fcfs', program=enums.Program.HIKING.value
        )
        runner = run.SingleTripLotteryRunner(trip)

        with patch.object(models.Trip, 'save', wraps=models.Trip.save) as save_trip:
            runner()  # Early exits because it's not a lottery trip
        save_trip.assert_not_called()  # Trip was not modified

        trip.refresh_from_db()
        self.assertIsNone(trip.lottery_log)  # No lottery was run!
        self.assertEqual(trip.algorithm, 'fcfs')

    def test_run_with_no_signups(self):
        """We still run the lottery when nobody signed up."""
        trip = factories.TripFactory.create(algorithm='lottery')
        runner = run.SingleTripLotteryRunner(trip)
        runner()
        trip.refresh_from_db()
        expected = '\n'.join(
            [
                'Randomly ordering (preference to MIT affiliates)...',
                'No participants signed up.',
                'Converting trip to first-come, first-serve.',
                '',
            ]
        )
        self.assertEqual(trip.algorithm, 'fcfs')
        self.assertEqual(trip.lottery_log, expected)

    # The wall time when invoking the lottery determines the random seed
    # See lottery.rank for more details
    @freeze_time("2019-10-22 10:30:00 EST")
    def test_run(self):
        """Test a full run of a single trip's lottery, demonstrating deterministic seeding.

        See lottery.rank for more detail on how the random seeding works.
        """
        trip = factories.TripFactory.create(
            pk=838249,  # Will factor into seed + ordering
            name="Single Trip Example",
            algorithm='lottery',
            maximum_participants=2,
            program=enums.Program.CLIMBING.value,
        )

        alice = factories.SignUpFactory.create(
            participant__pk=1021,  # Will factor into seed + ordering
            participant__name="Alice Aaronson",
            participant__affiliation=affiliations.MIT_UNDERGRAD.CODE,
            trip=trip,
            on_trip=False,
        )
        bob = factories.SignUpFactory.create(
            participant__pk=1022,  # Will factor into seed + ordering
            participant__name="Bob Bobberson",
            participant__affiliation=affiliations.MIT_AFFILIATE.CODE,
            trip=trip,
            on_trip=False,
        )
        charles = factories.SignUpFactory.create(
            participant__pk=1023,  # Will factor into seed + ordering
            participant__name="Charles Charleson",
            participant__affiliation=affiliations.NON_AFFILIATE.CODE,
            trip=trip,
            on_trip=False,
        )

        runner = run.SingleTripLotteryRunner(trip)
        runner()  # Early exits because it's not a lottery trip

        # We can expect the exact same ordering & "random" seed because:
        # - we mock wall time to be consistent with every test run
        # - we know participant PKs and the trip PK.
        # - we know the test environment's PRNG_SEED_SECRET
        self.assertEqual(settings.PRNG_SEED_SECRET, 'some-key-unknown-to-participants')
        expected = dedent(
            """\
            Randomly ordering (preference to MIT affiliates)...
            Participants will be handled in the following order:
              1. Alice Aaronson       (MIT undergrad, 0.04993458051632388)
              2. Charles Charleson    (Non-affiliate, 0.1895304657881689)
              3. Bob Bobberson        (MIT affiliate (staff or faculty), 0.5391638258147878)
            --------------------------------------------------
            Single Trip Example has 2 slots, adding Alice Aaronson
            Single Trip Example has 1 slot, adding Charles Charleson
            Adding Bob Bobberson to the waitlist
            """
        )

        # The lottery log explains what happened & is written directly to the trip.
        trip.refresh_from_db()
        self.assertEqual(trip.algorithm, 'fcfs')
        self.assertEqual(trip.lottery_log, expected)

        # Alice & Charles were placed on the trip.
        alice.refresh_from_db()
        self.assertTrue(alice.on_trip)
        charles.refresh_from_db()
        self.assertTrue(charles.on_trip)

        # Bob was waitlisted.
        bob.refresh_from_db()
        self.assertFalse(bob.on_trip)
        self.assertTrue(bob.waitlistsignup)


@freeze_time("2020-01-15 09:00:00 EST")
class WinterSchoolLotteryTests(TestCase):
    @staticmethod
    def _ws_trip(**kwargs):
        return factories.TripFactory.create(
            algorithm="lottery", program=enums.Program.WINTER_SCHOOL.value, **kwargs
        )

    def setUp(self):
        self.ice = self._ws_trip(
            name="Frankenstein",
            trip_type=enums.TripType.ICE_CLIMBING.value,
            maximum_participants=3,
            trip_date=date(2020, 1, 18),  # Sat
        )
        self.hike = self._ws_trip(
            name="Welch-Dickey",
            trip_type=enums.TripType.HIKING.value,
            maximum_participants=2,
            trip_date=date(2020, 1, 19),  # Sun
        )

        self.hiker = factories.ParticipantFactory.create(name="Prefers Hiking")
        self.climber = factories.ParticipantFactory.create(name="Seeks Ice")

        # Won't be included in the lottery run.
        self.non_ws = factories.TripFactory.create(
            name="Local trail work",
            algorithm="lottery",
            program=enums.Program.SERVICE.value,
            trip_type=enums.TripType.HIKING.value,
            trip_date=date(2020, 1, 18),  # Sat
        )

    def _assert_fcfs_at_noon(self, trip):
        self.assertEqual(trip.algorithm, 'fcfs')
        self.assertEqual(
            trip.signups_open_at, date_utils.localize(datetime(2020, 1, 15, 12))
        )

    def test_no_signups(self):
        """Trips are made FCFS, even if nobody signed up."""
        runner = run.WinterSchoolLotteryRunner()
        runner()

        for trip in [self.hike, self.ice]:
            trip.refresh_from_db()
            self._assert_fcfs_at_noon(trip)

    def test_non_ws_trips_ignored(self):
        """Participants with signups for non-WS trips are handled.

        Namely,
        - a participant's signup for a non-WS trip does not affect the lottery
        - The cleanup phase of the lottery does not modify any non-WS trips
        """
        outside_iap_trip = factories.TripFactory.create(
            name='non-WS trip',
            algorithm='lottery',
            program=enums.Program.WINTER_NON_IAP.value,
            trip_date=date(2020, 1, 18),
        )
        office_day = factories.TripFactory.create(
            name='Office Day',
            algorithm='fcfs',
            program=enums.Program.NONE.value,
            trip_date=date(2020, 1, 19),
        )

        # Sign up the hiker for all three trips!
        for trip in [self.hike, outside_iap_trip, office_day]:
            factories.SignUpFactory.create(participant=self.hiker, trip=trip)

        runner = run.WinterSchoolLotteryRunner()
        runner()

        # The participant was placed on their desired WS trip!
        ws_signup = models.SignUp.objects.get(trip=self.hike, participant=self.hiker)
        self.assertTrue(ws_signup.on_trip)

        # Neither of the other two trips had their algorithm or start time adjusted
        outside_iap_trip.refresh_from_db()
        self.assertEqual(outside_iap_trip.algorithm, 'lottery')
        office_day.refresh_from_db()
        self.assertEqual(office_day.signups_open_at, date_utils.local_now())
