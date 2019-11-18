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
        par.lotteryinfo = models.LotteryInfo(car_status="none")
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
        self.runner = run.WinterSchoolLotteryRunner()

    @staticmethod
    def _pair_signed_up_for(trip, car_status, order=None):
        one = factories.ParticipantFactory.create(name="Bert")
        two = factories.ParticipantFactory.create(name="Ernie")

        # Reciprocally pair them
        factories.LotteryInfoFactory.create(
            participant=one, car_status=car_status, paired_with=two
        )
        factories.LotteryInfoFactory.create(
            participant=two, car_status=car_status, paired_with=one
        )

        factories.SignUpFactory.create(participant=one, trip=trip, order=order)
        factories.SignUpFactory.create(participant=two, trip=trip, order=order)
        return (one, two)

    def _place_participant(self, par):
        if not hasattr(par, 'reciprocally_paired'):
            par = self._with_annotation(par.pk)
        handler = handle.WinterSchoolParticipantHandler(par, self.runner)
        return handler.place_participant()

    def test_no_signups(self):
        """ Attempting to place a participant with no chosen signups is handled.

        Note that (at time of writing) the ranker does not actually pass in any participants
        who lack signups this particular week (since the number of other participants is in
        the thousands).
        """
        par = factories.ParticipantFactory.create()
        self.assertEqual(
            self._place_participant(par),
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
        self.assertTrue(self.runner.handled(par))

    def test_plenty_of_room(self):
        """ Simplest case: participant's top choice has plenty of room. """
        par = factories.SignUpFactory.create(trip=self.trip).participant

        self._place_participant(par)
        self.assertTrue(self.runner.handled(par))
        self._assert_on_trip(par, self.trip)

    def test_reciprocally_paired(self):
        """ Handling a pair is only done once both have been seen. """
        # Two participants, paired with each other!
        john = factories.ParticipantFactory.create()
        alex = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=john, paired_with=alex)
        factories.LotteryInfoFactory.create(participant=alex, paired_with=john)

        factories.SignUpFactory.create(participant=john, trip=self.trip)
        factories.SignUpFactory.create(participant=alex, trip=self.trip)

        # John goes first, nothing is done because his partner hasn't been handled!
        self.assertIsNone(self._place_participant(john))
        self.assertTrue(self.runner.handled(john))
        self._assert_on_trip(john, self.trip, on_trip=False)

        # Once handling Alex, both are placed on their ideal trip.
        self.assertEqual(
            self._place_participant(alex),
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
        self.assertTrue(self.runner.handled(alex))
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

        # Place two other participants on the trips first, filling each
        for trip in [preferred_trip, second_trip]:
            signup = factories.SignUpFactory.create(trip=trip)
            self._place_participant(signup.participant)

        # Now, try to place the participant, even though both trips are full!
        info = self._place_participant(par)
        self.assertTrue(info['waitlisted'])
        signup = models.SignUp.objects.get(participant=par, trip=preferred_trip)
        self.assertFalse(signup.on_trip)
        self.assertTrue(signup.waitlistsignup)

    def test_driver_bump(self):
        """ Drivers can bump non-drivers off if it makes the trip possible. """
        trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=2,
        )

        driver = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=driver, car_status='own')
        factories.SignUpFactory.create(participant=driver, trip=trip)

        # Place two other people on the trip first!
        first = factories.ParticipantFactory()
        second = factories.ParticipantFactory()
        # Include a ranking override so that we guarantee first is ranked second
        # (This ensures that `second_signup` will be yanked for the driver)
        factories.LotteryAdjustmentFactory.create(participant=first, adjustment=-1)
        for par in [first, second]:
            factories.SignUpFactory.create(trip=trip, participant=par)
            self._place_participant(par)

        self._assert_on_trip(first, trip)
        self._assert_on_trip(second, trip)

        # Place the driver, observe that they get a spot since we needed drivers.
        self._place_participant(driver)
        self._assert_on_trip(driver, trip)

        # The last person on the trip was bumped off!
        self._assert_on_trip(second, trip, on_trip=False)

    def test_avoid_placing_if_risking_bump(self):
        """ We avoid placing participants on a top choice trip if they may be bumped! """
        # Trip has 3 slots, needs 2 drivers
        preferred_trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=3,
        )
        second_trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=1,
        )

        # Our participant is not a driver.
        par = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=par, car_status="none")

        # Sign up for and rank the two trips!
        factories.SignUpFactory.create(participant=par, trip=preferred_trip, order=1)
        factories.SignUpFactory.create(participant=par, trip=second_trip, order=2)

        # Put two participants on the trip - neither is a driver!
        # This leaves only one more spot remaining, and no drivers on the trip.
        for _i in range(2):
            signup = factories.SignUpFactory.create(trip=preferred_trip)
            self._place_participant(signup.participant)

        # When placing our participant, we opt for trip two - a driver wants the last spot
        driver = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=driver, car_status='own')
        factories.SignUpFactory.create(participant=driver, trip=preferred_trip)

        self._place_participant(par)
        self._assert_on_trip(par, second_trip)

    def test_avoid_placing_pair_if_risking_bump(self):
        """ We avoid placing a pair of participants on a top choice trip if they may be bumped!

        Instead, we fall back to putting them on their top-choice trip that has room for them.
        """
        # Trip has 3 slots, needs 2 drivers
        preferred_trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=3,
        )
        second_trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=10,
        )

        # Paired participants, neither are drivers.
        one, two = self._pair_signed_up_for(preferred_trip, car_status='none', order=1)
        factories.SignUpFactory.create(participant=one, trip=second_trip, order=2)
        factories.SignUpFactory.create(participant=two, trip=second_trip, order=2)

        # Put a non-driver on their preferred trip.
        # This leaves two spot remaining, and no drivers on the trip.
        self._place_participant(
            factories.SignUpFactory.create(trip=preferred_trip).participant
        )

        # When placing our pair, we opt for trip two! A driver would displace one of them.
        driver = factories.ParticipantFactory.create(name="Car Owner")
        factories.LotteryInfoFactory.create(participant=driver, car_status='own')
        factories.SignUpFactory.create(participant=driver, trip=preferred_trip)

        self.assertIsNone(self._place_participant(one))
        self._place_participant(two)

        self._assert_on_trip(one, second_trip)
        self._assert_on_trip(one, second_trip)
