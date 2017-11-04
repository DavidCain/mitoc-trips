import mock

from django.test import SimpleTestCase

from ws import models
from ws.utils import signups as signup_utils


# SimpleTestCase since all calls to `save` are mocked out
class ManualOrderingTests(SimpleTestCase):
    @mock.patch.object(models.SignUp, 'save')
    def test_manual_next(self, save):
        """ The manual ordering is applied when the signup is on a trip. """
        signup = models.SignUp(on_trip=True)
        signup_utils.next_in_order(signup, 3)

        save.assert_called_once()
        self.assertEqual(signup.manual_order, 3)

    @mock.patch('ws.models.Trip.last_of_priority', new_callable=mock.PropertyMock)
    def test_last_of_priority(self, last_of_priority):
        """ The signup is placed in last priority if already on trip.

        This makes the signup "priority," but below others.

        That is, leader-ordered signups should go above other signups. (Let's
        say that a leader is organizing signups, but new signups come in before
        they submit the ordering - we want to be sure all their ordering goes
        above any new signups).
        """
        last_of_priority.return_value = 5
        trip = models.Trip()

        with mock.patch.object(models.SignUp, 'save') as save:
            signup = models.SignUp(trip=trip, on_trip=True)
            signup_utils.next_in_order(signup, None)

        save.assert_called_once()
        self.assertEqual(signup.manual_order, 5)

    @mock.patch.object(models.SignUp, 'save')
    def test_no_waitlist_entry(self, save):
        """ When neither on the trip, nor the waitlist, nothing happens. """
        signup = models.SignUp()  # No corresponding waitlist entry

        for manual_order in [None, 3, 5]:
            signup_utils.next_in_order(signup, manual_order)
            save.assert_not_called()
            self.assertIsNone(signup.manual_order)

    @mock.patch.object(models.WaitListSignup, 'save')
    def test_wl_invert_manual_order(self, wl_save):
        """ Manual orderings are negative when updating waitlist entries.

        (nulls come after integers when reverse sorted, so anyone with a manual
        ordering integer will be first)
        """
        signup = models.SignUp(waitlistsignup=models.WaitListSignup())
        signup_utils.next_in_order(signup, 4)

        wl_save.assert_called_once()
        self.assertEqual(signup.waitlistsignup.manual_order, -4)  # Negated!

    @mock.patch('ws.models.WaitList.last_of_priority', new_callable=mock.PropertyMock)
    @mock.patch.object(models.WaitListSignup, 'save')
    def test_wl_last_of_priority(self, wl_save, last_of_priority):
        """ If no manual order is passed, `last_in_priority` is used. """
        last_of_priority.return_value = 37
        wl_signup = models.WaitListSignup(waitlist=models.WaitList())
        signup = models.SignUp(waitlistsignup=wl_signup)

        signup_utils.next_in_order(signup, None)

        wl_save.assert_called_once()
        self.assertEqual(wl_signup.manual_order, 37)
