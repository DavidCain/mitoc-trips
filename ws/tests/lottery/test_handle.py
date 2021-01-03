from unittest import mock

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
    def _ws_trip(**kwargs):
        return factories.TripFactory.create(
            algorithm='lottery', program=enums.Program.WINTER_SCHOOL.value, **kwargs
        )

    @staticmethod
    def _with_annotation(participant_id):
        return annotate_reciprocally_paired(
            models.Participant.objects.filter(pk=participant_id)
        ).get()

    def _assert_on_trip(self, participant, trip, on_trip=True):
        signup = models.SignUp.objects.get(participant=participant, trip=trip)
        self.assertEqual(signup.on_trip, on_trip)

    @staticmethod
    def _reciprocally_pair(one, two):
        factories.LotteryInfoFactory.create(participant=one, paired_with=two)
        factories.LotteryInfoFactory.create(participant=two, paired_with=one)


class SingleTripPlacementTests(TestCase, Helpers):
    def test_reciprocally_paired(self):
        """ Handling a pair is only done once both have been seen. """
        trip = factories.TripFactory.create(
            algorithm='lottery', program=enums.Program.CLIMBING.value
        )
        # Two participants, paired with each other!
        john = factories.ParticipantFactory.create()
        alex = factories.ParticipantFactory.create()
        self._reciprocally_pair(john, alex)

        factories.SignUpFactory.create(participant=john, trip=trip)
        factories.SignUpFactory.create(participant=alex, trip=trip)

        john = self._with_annotation(john.pk)
        alex = self._with_annotation(alex.pk)

        runner = run.SingleTripLotteryRunner(trip)

        # John goes first, nothing is done because his partner hasn't been seen!
        john_handler = handle.SingleTripParticipantHandler(john, runner, trip)
        self.assertIsNone(john_handler.place_participant())
        self.assertTrue(runner.seen(john))
        self._assert_on_trip(john, trip, on_trip=False)

        # Once handling Alex, both are placed on their ideal trip.
        alex_handler = handle.SingleTripParticipantHandler(alex, runner, trip)
        alex_handler.place_participant()

        self.assertTrue(runner.seen(alex))
        self._assert_on_trip(john, trip)
        self._assert_on_trip(alex, trip)
        self.assertTrue(runner.handled(alex))
        self.assertTrue(runner.handled(john))


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
        self._reciprocally_pair(john, alex)

        factories.SignUpFactory.create(participant=john, trip=self.trip)
        factories.SignUpFactory.create(participant=alex, trip=self.trip)

        # John goes first, nothing is done because his partner hasn't been seen!
        self.assertIsNone(self._place_participant(john))
        self.assertTrue(self.runner.seen(john))
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
        self.assertTrue(self.runner.seen(alex))
        self._assert_on_trip(john, self.trip)
        self._assert_on_trip(alex, self.trip)
        self.assertTrue(self.runner.handled(alex))
        self.assertTrue(self.runner.handled(john))

    def test_reciprocally_paired_but_no_overlapping_trips(self):
        """ Participants must both sign up for the same trips to be considered. """
        john = factories.ParticipantFactory.create()
        alex = factories.ParticipantFactory.create()
        self._reciprocally_pair(john, alex)

        # John wants to go on the trip. Alex wants to go on another
        factories.SignUpFactory.create(participant=john, trip=self._ws_trip())
        factories.SignUpFactory.create(participant=alex, trip=self.trip)

        # Place both in succession. They won't be placed on a trip!
        self.assertIsNone(self._place_participant(john))
        alex_summary = self._place_participant(alex)
        self.assertFalse(
            models.SignUp.objects.filter(
                participant__pk__in={john.pk, alex.pk}, on_trip=True
            ).exists()
        )

        self.assertTrue(self.runner.handled(john))
        self.assertTrue(self.runner.handled(alex))

        self.assertEqual(
            alex_summary,
            {
                'participant_pk': alex.pk,
                'paired_with_pk': john.pk,
                'is_paired': True,
                'affiliation': 'NA',
                # Alex wasn't placed on any trip, or even waitlisted! (Neither was John)
                'ranked_trips': [self.trip.pk],
                'placed_on_choice': None,
                'waitlisted': False,
            },
        )

    def test_reciprocally_paired_only_some_overlapping_trips(self):
        """ Participants must both sign up for the same trips to be considered. """
        john = factories.ParticipantFactory.create()
        alex = factories.ParticipantFactory.create()
        self._reciprocally_pair(john, alex)

        # Both want to go on the same trip, but Alex would prefer to go on another.
        factories.SignUpFactory.create(participant=alex, trip=self.trip)
        other_trip = self._ws_trip()
        factories.SignUpFactory.create(participant=john, trip=other_trip)
        factories.SignUpFactory.create(participant=john, trip=self.trip)

        # Place both in succession. They will be placed on their shared trip
        self._place_participant(alex)
        john_summary = self._place_participant(john)

        self.assertTrue(self.runner.handled(john))
        self.assertTrue(self.runner.handled(alex))
        self._assert_on_trip(john, self.trip)
        self._assert_on_trip(alex, self.trip)

        self.assertEqual(
            john_summary,
            {
                'participant_pk': john.pk,
                'paired_with_pk': alex.pk,
                'is_paired': True,
                'affiliation': mock.ANY,
                # John ranked two trips! From his perspective, he had his second choice.
                'ranked_trips': [other_trip.pk, self.trip.pk],
                'placed_on_choice': 2,
                'waitlisted': False,
            },
        )

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

    def test_bump_but_only_one_driver(self):
        # Create a trip with room for only one participant
        trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=1,
        )

        # Two participants, both drivers
        dee = factories.ParticipantFactory.create()
        dum = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=dee, car_status='own')
        factories.LotteryInfoFactory.create(participant=dum, car_status='rent')
        factories.SignUpFactory.create(participant=dee, trip=trip)
        factories.SignUpFactory.create(participant=dum, trip=trip)

        # Place the driver first. We have one driver, which is short of the two we normally want
        self._place_participant(dee)
        self._assert_on_trip(dee, trip, on_trip=True)

        # Now try to place the other driver. They won't bump the first driver.
        self._place_participant(dum)
        self._assert_on_trip(dum, trip, on_trip=False)

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

    def test_bump_paired_participants(self):
        """ If a participant pair is bumped, we keep them on the same trip. """
        # Two paired participants rank two trips.
        preferred_trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=2,
        )
        second_trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            # Not enough room for both participants!
            # This is avoids possibly triggering the driver avoidance rule
            # (but has room for one of the bumped participants)
            maximum_participants=1,
        )
        one, two = self._pair_signed_up_for(preferred_trip, car_status='none', order=1)
        factories.SignUpFactory.create(participant=one, trip=second_trip, order=2)
        factories.SignUpFactory.create(participant=two, trip=second_trip, order=2)

        # Paired participants are placed on their preferred trip
        self.assertIsNone(self._place_participant(one))  # par one not placed
        self._place_participant(two)
        self._assert_on_trip(one, preferred_trip)
        self._assert_on_trip(two, preferred_trip)

        # Driver comes along and bumps one of the pair.
        driver = factories.ParticipantFactory.create(name="Car Owner")
        factories.LotteryInfoFactory.create(participant=driver, car_status='own')
        factories.SignUpFactory.create(participant=driver, trip=preferred_trip)

        # Driver gets the trip, bumps one of the two.
        self._place_participant(driver)
        self._assert_on_trip(driver, preferred_trip)
        self.assertFalse(preferred_trip.open_slots)

        # Though there's room on the second trip, we chose to keep them together
        self.assertTrue(second_trip.open_slots)
        waitlisted_signup = preferred_trip.waitlist.signups.get()
        self.assertIn(waitlisted_signup.participant, [one, two])
        self._assert_on_trip(waitlisted_signup.participant, second_trip, on_trip=False)
        self._assert_on_trip(driver, preferred_trip)

    def test_bump_single_participant(self):
        """ We try to place a participant on less-preferred trips if possible. """
        (best, middle, worst) = [
            factories.TripFactory.create(
                algorithm='lottery',
                program=enums.Program.WINTER_SCHOOL.value,
                maximum_participants=1,
            )
            for i in range(3)
        ]

        par = factories.ParticipantFactory.create()
        factories.SignUpFactory.create(participant=par, trip=best, order=1)
        factories.SignUpFactory.create(participant=par, trip=middle, order=2)
        factories.SignUpFactory.create(participant=par, trip=worst, order=3)

        # Driver also wants to be on those three trips, in the same order
        driver = factories.ParticipantFactory.create(name="Car Renter")
        factories.LotteryInfoFactory.create(participant=driver, car_status='rent')
        factories.SignUpFactory.create(participant=driver, trip=best, order=1)
        factories.SignUpFactory.create(participant=driver, trip=middle, order=2)
        factories.SignUpFactory.create(participant=driver, trip=worst, order=3)

        # Because the driver could displace the participant on any of the three trips,
        # we just choose the first trip and hope for the best.
        self._place_participant(par)
        self._assert_on_trip(par, best)

        # We place the driver, who displaces the participant.
        self._place_participant(driver)
        self._assert_on_trip(driver, best)
        self._assert_on_trip(par, best, on_trip=False)

        # The participant is moved to their second-favorite trip, not waitlisted.
        self._assert_on_trip(par, middle)
        self.assertFalse(best.waitlist.signups.count())

    def test_enough_drivers_already_no_bump(self):
        """ Participants can safely be placed on the last spot of a trip with enough drivers. """
        trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=2,
        )

        # Two participants, both drivers (one leads, one attends)
        leader_driver = factories.ParticipantFactory.create()
        par_driver = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=leader_driver, car_status='own')
        factories.LotteryInfoFactory.create(participant=par_driver, car_status='rent')
        trip.leaders.add(leader_driver)

        # Place the driver first. We now have two drivers!
        factories.SignUpFactory.create(participant=par_driver, trip=trip)
        self._place_participant(par_driver)
        self._assert_on_trip(par_driver, trip)

        # Non-driver wants to join the trip.
        par = factories.ParticipantFactory.create()
        factories.SignUpFactory.create(participant=par, trip=trip, order=1)
        factories.SignUpFactory.create(participant=par, order=2)  # Some other trip

        # Another driver has expressed interest in the trip. They could bump!
        other_driver = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=other_driver, car_status='own')
        factories.SignUpFactory.create(participant=other_driver, trip=trip)

        # The non-driver is the last spot! They *might* risk a bump from `other_driver`
        # However, the trip has 2 drivers so they are safe & will not be bumped.
        self._place_participant(par)
        self._assert_on_trip(par, trip)

    def test_second_to_last_spot_no_bump(self):
        """ Participants can be placed on the second-to-last spot without risking bump. """
        trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=2,
        )

        # Leader is a driver.
        leader_driver = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=leader_driver, car_status='own')
        trip.leaders.add(leader_driver)

        # Non-driver wants to join the trip.
        par = factories.ParticipantFactory.create()
        factories.SignUpFactory.create(participant=par, trip=trip, order=1)
        factories.SignUpFactory.create(participant=par, order=2)  # Some other trip

        # Another driver has expressed interest in the trip. They won't bump.
        other_driver = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=other_driver, car_status='own')
        factories.SignUpFactory.create(participant=other_driver, trip=trip)

        # The non-driver is the second-to-last spot! They *might* risk a bump from `other_driver`
        # However, the leader is a driver. The last spot can be filled by a driver without bump.
        self._place_participant(par)
        self._assert_on_trip(par, trip)

    def test_bumped_bypassing_full_trip(self):
        """ If a participant is bumped, their other signups' trips may be full. """
        trip1, trip2, trip3 = [
            factories.TripFactory.create(
                name=f"Trip {i}",
                algorithm='lottery',
                program=enums.Program.WINTER_SCHOOL.value,
                maximum_participants=2,
            )
            for i in range(1, 4)
        ]

        # These two participants will be placed, one after the other
        other_par = factories.ParticipantFactory.create(affiliation="NA")
        par = factories.ParticipantFactory.create(affiliation="MU")
        # (submit lottery prefs, to cover all branches in `bump_participant()`)
        factories.LotteryInfoFactory.create(participant=par, car_status='none')

        # Assert that the priority keys match the order in which we'll assign these two.
        # (when identifying the lowest non-driver, we look to priority keys)
        adjust = factories.LotteryAdjustmentFactory.create(
            participant=other_par, adjustment=-1
        )
        # Lower is better, so see that the other participant is placed first.
        self.assertIn("boost", str(adjust))
        ranker = self.runner.ranker
        assert ranker.priority_key(other_par) < ranker.priority_key(par)

        # A driver expressed interest in each trip (making each trip potentially "bumpable")
        driver = factories.ParticipantFactory.create()
        factories.LotteryInfoFactory.create(participant=driver, car_status='own')
        for trip in [trip1, trip2, trip3]:
            factories.SignUpFactory.create(participant=driver, trip=trip)

        # A non-driver joins the trip first. One slot remains!
        factories.SignUpFactory.create(participant=other_par, trip=trip1)
        self._place_participant(other_par)

        # Another non-driver ranks this trip as their favorite.
        # They rank two other trips below. They risk getting bumped from each trip.
        factories.SignUpFactory.create(participant=par, trip=trip1, order=1)
        factories.SignUpFactory.create(participant=par, trip=trip2, order=2)
        factories.SignUpFactory.create(participant=par, trip=trip3, order=3)

        # There are no safe trips, so we place them on the last spot for their top trip & hope.
        self._place_participant(par)
        self._assert_on_trip(par, trip1)
        self._assert_on_trip(par, trip2, on_trip=False)
        self._assert_on_trip(par, trip3, on_trip=False)

        # Other participants take the last spots on trip 2, filling the trip
        for _i in range(2):
            signup = factories.SignUpFactory.create(trip=trip2)
            self._place_participant(signup.participant)

        # The main par had the lowest lottery key so they're the one that should be bumped
        self.assertEqual(self.runner.signup_to_bump(trip1).participant.pk, par.pk)

        # Now, we place the driver, who will bump the participant from trip one.
        # Trip 2 is full, so we place the bumped participant onto trip 3.
        self._place_participant(driver)
        self._assert_on_trip(driver, trip1)
        self._assert_on_trip(par, trip3)

    def test_driver_cannot_bump_full_trip_with_enough_drivers(self):
        """ Drivers may not bump a trip with enough drivers on it. """
        trip = factories.TripFactory.create(
            algorithm='lottery',
            program=enums.Program.WINTER_SCHOOL.value,
            maximum_participants=3,
        )

        # Two drivers take the first two spots
        for _i in range(2):
            driver = factories.ParticipantFactory.create()
            factories.LotteryInfoFactory.create(participant=driver, car_status='own')
            factories.SignUpFactory.create(participant=driver, trip=trip)
            self._place_participant(driver)

        # A non-driver takes the last spot
        non_driver = factories.ParticipantFactory.create()
        factories.SignUpFactory.create(participant=non_driver, trip=trip)
        self._place_participant(non_driver)
        self._assert_on_trip(non_driver, trip)

        # A driver wants to be placed on this trip, but it's full. They do not bump.
        main_driver = factories.ParticipantFactory.create()
        factories.SignUpFactory.create(participant=main_driver, trip=trip)
        self._place_participant(main_driver)

        self._assert_on_trip(main_driver, trip, on_trip=False)
