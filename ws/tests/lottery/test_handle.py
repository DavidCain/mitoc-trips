from django.test import SimpleTestCase

from ws import enums, models
from ws.lottery import annotate_reciprocally_paired, handle, run
from ws.tests import TestCase, factories


class DriverTests(SimpleTestCase):
    def test_no_lotteryinfo(self):
        """ Don't regard anybody as a driver if they didn't submit prefs. """
        par = factories.ParticipantFactory.build()
        self.assertFalse(handle.par_is_driver(par))

    def test_lotteryinfo(self):
        """ Drivers are based off car status from that week. """
        par = factories.ParticipantFactory.build()
        par.lotteryinfo = factories.LotteryInfoFactory.build(car_status=None)
        self.assertFalse(handle.par_is_driver(par))

        par.lotteryinfo = models.LotteryInfo(car_status='own')
        self.assertTrue(handle.par_is_driver(par))
        par.lotteryinfo = models.LotteryInfo(car_status='rent')
        self.assertTrue(handle.par_is_driver(par))


class Helpers:
    @staticmethod
    def _with_annotation(participant_id):
        return annotate_reciprocally_paired(
            models.Participant.objects.filter(pk=participant_id)
        ).get()

    def _assert_on_trip(self, participant, trip, on_trip=True):
        signup = models.SignUp.objects.get(participant=participant, trip=trip)
        self.assertEqual(signup.on_trip, on_trip)


class SingleTripPlacementTests(TestCase, Helpers):
    def test_reciprocally_paired(self):
        """ Handling a pair is only done once both have been seen. """
        trip = factories.TripFactory.create(
            algorithm='lottery', program=enums.Program.CLIMBING.value
        )
        # Two participants, paired with each other!
        john = factories.ParticipantFactory.create()
        alex = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=john, paired_with=alex)
        factories.LotteryInfoFactory.create(participant=alex, paired_with=john)

        factories.SignUpFactory.create(participant=john, trip=trip)
        factories.SignUpFactory.create(participant=alex, trip=trip)

        john = self._with_annotation(john.pk)
        alex = self._with_annotation(alex.pk)

        runner = run.SingleTripLotteryRunner(trip)

        # John goes first, nothing is done because his partner hasn't been handled!
        john_handler = handle.SingleTripParticipantHandler(john, runner, trip)
        self.assertIsNone(john_handler.place_participant())
        self.assertTrue(runner.handled(john))
        self._assert_on_trip(john, trip, on_trip=False)

        # Once handling Alex, both are placed on their ideal trip.
        alex_handler = handle.SingleTripParticipantHandler(alex, runner, trip)
        alex_handler.place_participant()

        self.assertTrue(runner.handled(alex))
        self._assert_on_trip(john, trip)
        self._assert_on_trip(alex, trip)


class WinterSchoolPlacementTests(TestCase, Helpers):
    def setUp(self):
        self.trip = factories.TripFactory.create(
            algorithm='lottery', program=enums.Program.WINTER_SCHOOL.value
        )

    def test_no_signups(self):
        """ Attempting to place a participant with no chosen signups is handled.

        Note that (at time of writing) the ranker does not actually pass in any participants
        who lack signups this particular week (since the number of other participants is in
        the thousands).
        """
        par = factories.ParticipantFactory.create()
        par = self._with_annotation(par.pk)
        runner = run.WinterSchoolLotteryRunner()
        handler = handle.WinterSchoolParticipantHandler(par, runner)
        self.assertEqual(
            handler.place_participant(),
            {
                'participant_pk': par.pk,
                'paired_with_pk': None,
                'is_paired': False,
                'affiliation': 'NA',
                'ranked_trips': [],
                'placed_on_choice': None,
                'waitlisted': False,
            },
        )
        self.assertTrue(runner.handled(par))

    def test_plenty_of_room(self):
        """ Simplest case: participant's top choice has plenty of room. """
        signup = factories.SignUpFactory.create(trip=self.trip)
        participant = self._with_annotation(signup.participant_id)

        runner = run.WinterSchoolLotteryRunner()
        handler = handle.WinterSchoolParticipantHandler(participant, runner)

        handler.place_participant()
        self.assertTrue(runner.handled(participant))
        self._assert_on_trip(participant, self.trip)

    def test_reciprocally_paired(self):
        """ Handling a pair is only done once both have been seen. """
        # Two participants, paired with each other!
        john = factories.ParticipantFactory.create()
        alex = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=john, paired_with=alex)
        factories.LotteryInfoFactory.create(participant=alex, paired_with=john)

        factories.SignUpFactory.create(participant=john, trip=self.trip)
        factories.SignUpFactory.create(participant=alex, trip=self.trip)

        john = self._with_annotation(john.pk)
        alex = self._with_annotation(alex.pk)

        runner = run.WinterSchoolLotteryRunner()

        # John goes first, nothing is done because his partner hasn't been handled!
        john_handler = handle.WinterSchoolParticipantHandler(john, runner)
        self.assertIsNone(john_handler.place_participant())
        self.assertTrue(runner.handled(john))
        self._assert_on_trip(john, self.trip, on_trip=False)

        # Once handling Alex, both are placed on their ideal trip.
        alex_handler = handle.WinterSchoolParticipantHandler(alex, runner)
        self.assertEqual(
            alex_handler.place_participant(),
            {
                'participant_pk': alex.pk,
                'paired_with_pk': john.pk,
                'affiliation': "NA",
                'is_paired': True,
                'ranked_trips': [self.trip.pk],
                'placed_on_choice': 1,
                'waitlisted': False,
            },
        )
        self.assertTrue(runner.handled(alex))
        self._assert_on_trip(john, self.trip)
        self._assert_on_trip(alex, self.trip)

    def test_waitlisted(self):
        """ If your preferred trips are all full, you'll be waitlisted. """
        preferred_trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=1,
        )
        second_trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=1,
        )

        # Sign up for and rank the two trips
        par = factories.ParticipantFactory.create()
        factories.SignUpFactory.create(participant=par, trip=preferred_trip, order=1)
        factories.SignUpFactory.create(participant=par, trip=second_trip, order=2)

        runner = run.WinterSchoolLotteryRunner()

        # Place two other participants on the trips first, filling each
        for trip in [preferred_trip, second_trip]:
            signup = factories.SignUpFactory.create(trip=trip)
            other_par = self._with_annotation(signup.participant_id)
            handler = handle.WinterSchoolParticipantHandler(other_par, runner)
            handler.place_participant()

        # Now, try to place the participant, even though both trips are full!
        participant = self._with_annotation(par.pk)
        handler = handle.WinterSchoolParticipantHandler(participant, runner)
        info = handler.place_participant()
        self.assertTrue(info['waitlisted'])
        signup = models.SignUp.objects.get(participant=participant, trip=preferred_trip)
        self.assertFalse(signup.on_trip)
        self.assertTrue(signup.waitlistsignup)

    def test_driver_bump(self):
        """ Drivers can bump non-drivers off if it makes the trip possible. """
        trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=2,
        )

        lotteryinfo = factories.LotteryInfoFactory.create(car_status='own')
        driver = self._with_annotation(lotteryinfo.participant_id)

        factories.SignUpFactory.create(participant=driver, trip=trip)

        # Place two other people on the trip first
        runner = run.WinterSchoolLotteryRunner()
        first_signup = factories.SignUpFactory.create(trip=trip)
        second_signup = factories.SignUpFactory.create(trip=trip)
        for signup in [first_signup, second_signup]:
            other_par = self._with_annotation(signup.participant_id)
            handler = handle.WinterSchoolParticipantHandler(other_par, runner)
            handler.place_participant()
        self._assert_on_trip(first_signup.participant, trip)
        self._assert_on_trip(second_signup.participant, trip)

        # Place the driver, observe that they get a spot since we needed drivers.
        handler = handle.WinterSchoolParticipantHandler(driver, runner)
        handler.place_participant()
        self._assert_on_trip(driver, trip)

        # The last person on the trip was bumped off!
        self._assert_on_trip(second_signup.participant, trip, on_trip=False)
