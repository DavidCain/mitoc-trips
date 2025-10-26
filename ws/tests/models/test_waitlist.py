from django.test import TestCase

from ws import models
from ws.tests import factories


class OrderingTests(TestCase):
    def test_created_first(self) -> None:
        """Without manual ordering, waitlist signups are ordered by creation time."""
        trip = factories.TripFactory.create()

        # Order in which the signups are created will not determine waitlist order!
        spot_2 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_1 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_4 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_3 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        # Demonstrate that signups are sorted by time of creation (since none have manual order)
        self.assertEqual(
            list(models.SignUp.objects.filter(trip=trip)),
            [spot_2, spot_1, spot_4, spot_3],
        )

        # However, when we create waitlist signups, they're sorted by time of addition
        for signup in [spot_1, spot_2, spot_3, spot_4]:
            factories.WaitListSignupFactory.create(signup=signup)

        self.assertEqual(list(trip.waitlist.signups), [spot_1, spot_2, spot_3, spot_4])

    def test_model_ordering(self) -> None:
        """We can manually order some waitlist signups.

        The primary use case for manually re-ordering the waitlist is for when a
        participant who was previously on the trip has to be removed for some reason
        (lack of cars, is one example). Out of fairness, we manually order to the top.
        """
        trip = factories.TripFactory.create()

        # Order in which the signups are created will not determine waitlist order!
        spot_2 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_1 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_4 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        spot_3 = factories.SignUpFactory.create(trip=trip, on_trip=False)
        # Demonstrate that signups are sorted by time of creation (since none have manual order)
        self.assertEqual(
            list(models.SignUp.objects.filter(trip=trip)),
            [spot_2, spot_1, spot_4, spot_3],
        )

        # Use a mix of manual ordering & falling back on ranking by creation time
        factories.WaitListSignupFactory.create(signup=spot_3, manual_order=None)
        factories.WaitListSignupFactory.create(signup=spot_2, manual_order=10)
        factories.WaitListSignupFactory.create(signup=spot_1, manual_order=11)
        factories.WaitListSignupFactory.create(signup=spot_4, manual_order=None)

        self.assertEqual(list(trip.waitlist.signups), [spot_1, spot_2, spot_3, spot_4])
