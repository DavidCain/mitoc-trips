from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from freezegun import freeze_time

from ws import enums
from ws.tests import TestCase, factories
from ws.utils.dates import localize


class LotteryRulesTest(SimpleTestCase):
    def test_single_trip_pairing_winter_school(self):
        """If a former lottery trip is now FCFS, we don't consider pairing."""
        fcfs_trip = factories.TripFactory.build(
            algorithm='lottery', program=enums.Program.WINTER_SCHOOL
        )
        self.assertFalse(fcfs_trip.single_trip_pairing)

    def test_single_trip_pairing_but_fcfs(self):
        """If a former lottery trip is now FCFS, we don't consider pairing."""
        fcfs_trip = factories.TripFactory.build(
            algorithm='fcfs', honor_participant_pairing=True
        )
        self.assertFalse(fcfs_trip.single_trip_pairing)

    def test_single_trip_pairing_lottery(self):
        does_honor = factories.TripFactory.build(
            program=enums.Program.CLIMBING.value,
            algorithm='lottery',
            honor_participant_pairing=True,
        )
        self.assertTrue(does_honor.single_trip_pairing)

        does_not_honor = factories.TripFactory.build(
            program=enums.Program.CLIMBING.value,
            algorithm='lottery',
            honor_participant_pairing=False,
        )
        self.assertFalse(does_not_honor.single_trip_pairing)


class FeedbackWindowTripTest(SimpleTestCase):
    @freeze_time("2019-10-22 10:30:00 EST")
    def test_past_trip(self):
        old_trip = factories.TripFactory.build(trip_date=date(2019, 9, 18))
        self.assertTrue(old_trip.feedback_window_passed)

    @freeze_time("2019-10-22 10:30:00 EST")
    def test_future_trip(self):
        future_trip = factories.TripFactory.build(trip_date=date(2020, 1, 1))
        self.assertFalse(future_trip.feedback_window_passed)


class OtherTripsByParticipantTest(TestCase):
    def setUp(self):
        """Make three trips, and three participants signed up for a subset of each."""

        def _place_on_trip(trip, par):
            return factories.SignUpFactory.create(
                trip=trip, participant=par, on_trip=True
            )

        # These will be ordered by date (2 -> 1 -> 3)
        self.trip_1 = factories.TripFactory.create(trip_date=date(2019, 11, 23))
        self.trip_2 = factories.TripFactory.create(trip_date=date(2019, 11, 22))
        self.trip_3 = factories.TripFactory.create(trip_date=date(2019, 11, 24))

        # First participant is only on this trip!
        self.par_1 = factories.ParticipantFactory.create(name="Trip One")
        _place_on_trip(self.trip_1, self.par_1)

        # Second participant is signed up for two trips.
        self.par_1_2 = factories.ParticipantFactory.create(name="Two Trips")
        _place_on_trip(self.trip_1, self.par_1_2)
        _place_on_trip(self.trip_2, self.par_1_2)

        # Third participant is a participant for two trips, leader on another!
        self.par_1_2_3 = factories.ParticipantFactory.create(name="All Three")
        _place_on_trip(self.trip_1, self.par_1_2_3)
        self.trip_2.leaders.add(self.par_1_2_3)
        _place_on_trip(self.trip_3, self.par_1_2_3)

    def test_nobody_on_trip(self):
        trip = factories.TripFactory.create()
        self.assertCountEqual(trip.other_trips_by_participant(), [])

    def test_success(self):
        self.assertCountEqual(
            self.trip_1.other_trips_by_participant(),
            [
                (self.par_1.pk, []),
                (self.par_1_2.pk, [self.trip_2]),
                (self.par_1_2_3.pk, [self.trip_2, self.trip_3]),
            ],
        )

        # The only participant on trip 3 is also on two other trips (leading one!)
        self.assertCountEqual(
            self.trip_3.other_trips_by_participant(),
            [(self.par_1_2_3.pk, [self.trip_2, self.trip_1])],
        )

        # Trip 2 has one participant on it. The leader isn't included!
        self.assertCountEqual(
            self.trip_2.other_trips_by_participant(), [(self.par_1_2.pk, [self.trip_1])]
        )

    def test_future_trips_not_counted(self):
        # Far distant signup
        factories.SignUpFactory.create(
            participant=self.par_1, on_trip=True, trip__trip_date=date(2020, 1, 1)
        )

        # 4 days before & after the trip in question
        for trip_date in [date(2019, 11, 19), date(2019, 11, 27)]:
            factories.SignUpFactory.create(
                participant=self.par_1, on_trip=True, trip__trip_date=trip_date
            )

        # Participant one being on other (distant) trips is not factored in.
        self.assertCountEqual(
            self.trip_1.other_trips_by_participant(for_participants=[self.par_1]),
            [(self.par_1.pk, [])],
        )

        self.assertCountEqual(
            self.trip_1.other_trips_by_participant(),
            [
                (self.par_1.pk, []),
                (self.par_1_2.pk, [self.trip_2]),
                (self.par_1_2_3.pk, [self.trip_2, self.trip_3]),
            ],
        )


class CleanTest(SimpleTestCase):
    @freeze_time("2020-01-16 18:45:22 EST")
    def test_winter_school_trip_between_lotteries(self):
        """Any Winter School trip made between lotteries becomes a FCFS trip."""
        # This is a last-minute trip, will be coerced to FCFS
        trip = factories.TripFactory.build(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL,
            trip_date=date(2020, 1, 18),
        )
        trip.clean()
        self.assertEqual(trip.algorithm, 'fcfs')

        # Will have time to run in the lottery on Wed, Jan 22
        normal_trip = factories.TripFactory.build(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL,
            trip_date=date(2020, 1, 25),
        )
        normal_trip.clean()
        self.assertEqual(normal_trip.algorithm, 'lottery')

    @freeze_time("2020-01-16 18:45:22 EST")
    def test_non_winter_school_trip_between_lotteries(self):
        """We don't affect the lottery algorithm for non-WS trips!"""
        # This is a last-minute trip, but it will remain 'lottery' since it's not WS
        trip = factories.TripFactory.build(
            algorithm='lottery',
            program=enums.Program.SERVICE,
            trip_date=date(2020, 1, 18),
        )
        trip.clean()
        self.assertEqual(trip.algorithm, 'lottery')

    @freeze_time("2020-01-16 18:45:22 EST")
    def test_signups_closed_already(self):
        trip = factories.TripFactory.build(
            signups_close_at=localize(datetime(2020, 1, 15, 12, 0)),
            trip_date=date(2020, 1, 18),
        )
        self.assertIsNone(trip.time_created)
        self.assertTrue(trip.signups_closed)
        with self.assertRaises(ValidationError) as cm:
            trip.clean()
        self.assertEqual(cm.exception.message, "Signups can't be closed already!")

    @freeze_time("2020-01-16 18:45:22 EST")
    def test_trip_in_past(self):
        trip = factories.TripFactory.build(
            signups_close_at=None, trip_date=date(2020, 1, 14)
        )
        with self.assertRaises(ValidationError) as cm:
            trip.clean()
        self.assertEqual(cm.exception.message, "Trips can't occur in the past!")

    @freeze_time("2020-01-14 18:45:22 EST")
    def test_opens_after_closing(self):
        trip = factories.TripFactory.build(
            signups_open_at=localize(datetime(2020, 1, 15, 12, 0)),
            signups_close_at=localize(datetime(2020, 1, 15, 2, 0)),
            trip_date=date(2020, 1, 20),
        )
        with self.assertRaises(ValidationError) as cm:
            trip.clean()
        self.assertEqual(cm.exception.message, 'Trips cannot open after they close.')


class TripDatesTest(SimpleTestCase):
    @freeze_time("2020-01-16 18:45:22 EST")
    def test_less_than_a_week_away(self):

        past_trip = factories.TripFactory.build(trip_date=date(2020, 1, 15))
        self.assertFalse(past_trip.less_than_a_week_away)

        today_trip = factories.TripFactory.build(trip_date=date(2020, 1, 16))
        self.assertFalse(today_trip.less_than_a_week_away)

        tomorrow_trip = factories.TripFactory.build(trip_date=date(2020, 1, 17))
        self.assertTrue(tomorrow_trip.less_than_a_week_away)

        # Today (the 16th) is Thursday. The 23rd is also a Thursday.
        next_week_trip = factories.TripFactory.build(trip_date=date(2020, 1, 23))
        self.assertFalse(next_week_trip.less_than_a_week_away)

        # The 22nd is the closest Wednesday!
        next_wed_trip = factories.TripFactory.build(trip_date=date(2020, 1, 22))
        self.assertTrue(next_wed_trip.less_than_a_week_away)

        next_month_trip = factories.TripFactory.build(trip_date=date(2020, 2, 16))
        self.assertFalse(next_month_trip.less_than_a_week_away)
