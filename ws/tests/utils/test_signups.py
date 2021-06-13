from unittest.mock import PropertyMock, patch

from django.contrib import messages
from django.test import RequestFactory, SimpleTestCase

from ws import models
from ws.tests import TestCase, factories
from ws.utils import signups as signup_utils


# SimpleTestCase since all calls to `save` are mocked out
class ManualOrderingTests(SimpleTestCase):
    @patch.object(models.SignUp, 'save')
    def test_manual_next(self, save):
        """The manual ordering is applied when the signup is on a trip."""
        signup = models.SignUp(on_trip=True)
        signup_utils.next_in_order(signup, 3)

        save.assert_called_once()
        self.assertEqual(signup.manual_order, 3)

    @patch('ws.models.Trip.last_of_priority', new_callable=PropertyMock)
    def test_last_of_priority(self, last_of_priority):
        """The signup is placed in last priority if already on trip.

        This makes the signup "priority," but below others.

        That is, leader-ordered signups should go above other signups. (Let's
        say that a leader is organizing signups, but new signups come in before
        they submit the ordering - we want to be sure all their ordering goes
        above any new signups).
        """
        last_of_priority.return_value = 5
        trip = models.Trip()

        with patch.object(models.SignUp, 'save') as save:
            signup = models.SignUp(trip=trip, on_trip=True)
            signup_utils.next_in_order(signup, None)

        save.assert_called_once()
        self.assertEqual(signup.manual_order, 5)

    @patch.object(models.SignUp, 'save')
    def test_no_waitlist_entry(self, save):
        """When neither on the trip, nor the waitlist, nothing happens."""
        signup = models.SignUp()  # No corresponding waitlist entry

        for manual_order in [None, 3, 5]:
            signup_utils.next_in_order(signup, manual_order)
            save.assert_not_called()
            self.assertIsNone(signup.manual_order)

    @patch.object(models.WaitListSignup, 'save')
    def test_wl_invert_manual_order(self, wl_save):
        """Manual orderings are negative when updating waitlist entries.

        (nulls come after integers when reverse sorted, so anyone with a manual
        ordering integer will be first)
        """
        signup = models.SignUp(waitlistsignup=models.WaitListSignup())
        signup_utils.next_in_order(signup, 4)

        wl_save.assert_called_once()
        self.assertEqual(signup.waitlistsignup.manual_order, -4)  # Negated!

    @patch('ws.models.WaitList.last_of_priority', new_callable=PropertyMock)
    @patch.object(models.WaitListSignup, 'save')
    def test_wl_last_of_priority(self, wl_save, last_of_priority):
        """If no manual order is passed, `last_in_priority` is used."""
        last_of_priority.return_value = 37
        wl_signup = models.WaitListSignup(waitlist=models.WaitList())
        signup = models.SignUp(waitlistsignup=wl_signup)

        signup_utils.next_in_order(signup, None)

        wl_save.assert_called_once()
        self.assertEqual(wl_signup.manual_order, 37)


class NonTripParticipantsTests(TestCase):
    def test_creator_is_eligible_as_participant(self):
        """So long as the creator is not a leader, they count as a non-trip participant."""
        trip = factories.TripFactory()
        self.assertNotIn(trip.creator, trip.leaders.all())
        self.assertIn(trip.creator, signup_utils.non_trip_participants(trip))

        trip.leaders.add(trip.creator)

        self.assertIn(trip.creator, trip.leaders.all())
        self.assertNotIn(trip.creator, signup_utils.non_trip_participants(trip))

    def test_participants_on_trip(self):
        """All participants not signed up for the trip are returned."""
        trip = factories.TripFactory()
        on_trip = factories.ParticipantFactory.create()
        factories.SignUpFactory.create(participant=on_trip, trip=trip, on_trip=True)
        off_trip = factories.ParticipantFactory.create()
        signed_up_not_on_trip = factories.ParticipantFactory.create()
        factories.SignUpFactory.create(
            participant=signed_up_not_on_trip, trip=trip, on_trip=False
        )

        other_trip_signup = factories.SignUpFactory.create(on_trip=True)

        participants = signup_utils.non_trip_participants(trip)
        self.assertNotIn(on_trip, participants)
        self.assertIn(off_trip, participants)
        self.assertIn(signed_up_not_on_trip, participants)
        self.assertIn(other_trip_signup.participant, participants)


class AddToWaitlistTests(TestCase):
    def test_already_on_trip(self):
        """Participants already on the trip will be waitlisted."""
        signup = factories.SignUpFactory.create(on_trip=True)
        wl_signup = signup_utils.add_to_waitlist(signup)
        self.assertEqual(wl_signup.signup, signup)
        self.assertFalse(wl_signup.signup.on_trip)

    def test_already_has_waitlist_entry(self):
        wl_signup = factories.WaitListSignupFactory.create()
        self.assertIs(wl_signup, signup_utils.add_to_waitlist(wl_signup.signup))

    def test_adds_message_on_request(self):
        request = RequestFactory().get('/')
        signup = factories.SignUpFactory.create(on_trip=False)
        with patch.object(messages, 'success') as success:
            wl_signup = signup_utils.add_to_waitlist(signup, request=request)
        success.assert_called_once_with(request, "Added to waitlist.")
        self.assertEqual(wl_signup.signup, signup)
        self.assertFalse(wl_signup.signup.on_trip)

    def test_can_add_to_top_of_list(self):
        """We can add somebody to the waitlist, passing all others."""
        trip = factories.TripFactory()

        # Build a waitlist with a mixture of ordered by time added & manually ordered
        spot_1 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_2 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_3 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_4 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        factories.WaitListSignupFactory(signup=spot_3)
        factories.WaitListSignupFactory(signup=spot_4)
        factories.WaitListSignupFactory(signup=spot_2, manual_order=10)
        factories.WaitListSignupFactory(signup=spot_1, manual_order=11)
        self.assertEqual(list(trip.waitlist.signups), [spot_1, spot_2, spot_3, spot_4])

        signup = factories.SignUpFactory.create(trip=trip, on_trip=True)
        signup_utils.add_to_waitlist(signup, prioritize=True, top_spot=True)
        self.assertEqual(
            list(trip.waitlist.signups), [signup, spot_1, spot_2, spot_3, spot_4]
        )

    def test_can_add_to_bottom_of_priority(self):
        """Adding signups with priority puts them beneath other priorities, but above non."""
        trip = factories.TripFactory()

        spot_3 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_1 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_2 = factories.SignUpFactory.create(trip=trip, on_trip=False)

        # Start with a simple waitlist with no manual ordering
        spot_5 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_4 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        signup_utils.add_to_waitlist(spot_4)
        signup_utils.add_to_waitlist(spot_5)
        self.assertEqual(list(trip.waitlist.signups), [spot_4, spot_5])

        # Add each new signup to priority, but not the top spot
        signup_utils.add_to_waitlist(spot_1, prioritize=True, top_spot=False)
        self.assertEqual(list(trip.waitlist.signups), [spot_1, spot_4, spot_5])
        signup_utils.add_to_waitlist(spot_2, prioritize=True, top_spot=False)
        self.assertEqual(list(trip.waitlist.signups), [spot_1, spot_2, spot_4, spot_5])
        signup_utils.add_to_waitlist(spot_3, prioritize=True, top_spot=False)
        self.assertEqual(
            list(trip.waitlist.signups), [spot_1, spot_2, spot_3, spot_4, spot_5]
        )

        # Adding to the top spot still works!
        signup = factories.SignUpFactory.create(trip=trip, on_trip=True)
        signup_utils.add_to_waitlist(signup, prioritize=True, top_spot=True)
        self.assertEqual(
            list(trip.waitlist.signups),
            [signup, spot_1, spot_2, spot_3, spot_4, spot_5],
        )


class UpdateQueuesTest(TestCase):
    def test_lottery_trips_ignored(self):
        trip = factories.TripFactory.create(algorithm='lottery')

        signup = factories.SignUpFactory.create(trip=trip)

        self.assertTrue(trip.signups_open)
        self.assertFalse(signup.on_trip)

        signup_utils.update_queues_if_trip_open(trip)

        signup.refresh_from_db()
        self.assertFalse(signup.on_trip)

    def test_full_trip_expanding(self):
        """If a full trip expands, we pull participants from the waitlist!"""
        trip = factories.TripFactory.create(algorithm='fcfs', maximum_participants=2)
        self.assertTrue(trip.signups_open)

        one, two, three = (factories.SignUpFactory.create(trip=trip) for i in range(3))

        # First two participants placed
        signup_utils.trip_or_wait(one)
        signup_utils.trip_or_wait(two)
        self.assertTrue(one.on_trip)
        self.assertTrue(two.on_trip)

        # Third participant waitlisted
        signup_utils.trip_or_wait(three)
        self.assertFalse(three.on_trip)
        self.assertTrue(three.waitlistsignup)

        # An additional participant has the last spot on the waitlist.
        stays_on_wl = factories.SignUpFactory.create(trip=trip)
        signup_utils.trip_or_wait(stays_on_wl)

        # Update, explicitly avoiding signals
        models.Trip.objects.filter(pk=trip.pk).update(maximum_participants=3)
        trip.refresh_from_db()

        # Update the queues, our third participant can be on the trip now!
        signup_utils.update_queues_if_trip_open(trip)
        three.refresh_from_db()
        self.assertTrue(three.on_trip)
        # The third participant is pulled off the waitlist, the last stays on  the trip.
        self.assertCountEqual(
            models.WaitListSignup.objects.filter(signup__trip=trip),
            [stays_on_wl.waitlistsignup],
        )

    def test_full_trip_shrinking(self):
        trip = factories.TripFactory.create(algorithm='fcfs', maximum_participants=2)
        one = factories.SignUpFactory.create(trip=trip)
        two = factories.SignUpFactory.create(trip=trip)

        # First two participants placed
        signup_utils.trip_or_wait(one)
        signup_utils.trip_or_wait(two)
        self.assertTrue(one.on_trip)
        self.assertTrue(two.on_trip)

        # Update, explicitly avoiding signals, then update queues.
        models.Trip.objects.filter(pk=trip.pk).update(maximum_participants=1)
        trip.refresh_from_db()
        signup_utils.update_queues_if_trip_open(trip)

        # Last participant on the trip is bumped
        two.refresh_from_db()
        self.assertFalse(two.on_trip)

        wl_signup = models.WaitListSignup.objects.get(signup__trip=trip)
        self.assertEqual(wl_signup.signup, two)
