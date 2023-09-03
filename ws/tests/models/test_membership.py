from datetime import date

from django.test import SimpleTestCase
from freezegun import freeze_time

from ws import models
from ws.tests.factories import TripFactory


class MembershipActiveTests(SimpleTestCase):
    def test_null_membership_is_not_active(self):
        membership = models.Membership(membership_expires=None)
        self.assertFalse(membership.membership_active)

    @freeze_time("2018-11-19 01:00:00 EST")
    def test_past_membership_is_not_active(self):
        membership = models.Membership(membership_expires=date(2018, 11, 18))
        self.assertFalse(membership.membership_active)

    @freeze_time("2018-11-19 23:00:00 EST")
    def test_membership_valid_on_its_last_day(self):
        membership = models.Membership(membership_expires=date(2018, 11, 19))
        self.assertTrue(membership.membership_active)

    @freeze_time("2018-11-19 12:00:00 EST")
    def test_membership_valid_with_future_expiration(self):
        membership = models.Membership(membership_expires=date(2019, 10, 13))
        self.assertTrue(membership.membership_active)


@freeze_time("2019-10-19 12:00:00 EST")
class ShouldRenewForTripTests(SimpleTestCase):
    def _should_renew_for(
        self,
        trip: models.Trip,
        membership_expires: date,
    ) -> bool:
        membership = models.Membership(membership_expires=membership_expires)
        should_renew = membership.should_renew_for(trip)

        # Test some nice helper methods while we're at it
        if should_renew:
            # We should only recommend renewal if it's possible
            if membership_expires:
                self.assertTrue(membership.in_early_renewal_period)

            # First-time members *or* renewals should *always* be later than the trip
            self.assertGreater(membership.expiry_if_paid_today, trip.trip_date)

        return should_renew

    def test_mini_trips_not_covered(self):
        """Membership never needs to be renewed for 'mini trips'"""
        mini_trip = TripFactory.build(
            trip_date=date(2019, 11, 13), membership_required=False
        )
        for membership_expires in [
            date(2019, 10, 12),  # week before current date (currently expired!)
            date(2019, 11, 12),  # day before trip
            date(2019, 11, 13),  # day of trip
            date(2019, 11, 14),  # day after trip
        ]:
            self.assertFalse(self._should_renew_for(mini_trip, membership_expires))

    def test_trip_more_than_forty_days_out(self):
        """For trips more than 40 days out, we don't ask people to renew.

        NOTE: This test will fail if the constant RENEWAL_ALLOWED_WITH_DAYS_LEFT
        changes to be something larger than 40. That's desired, though - we'd like to
        know if that changes, so we can actively opt in to the changes.
        """
        # trip taking place 41 days in the future!
        future_trip = TripFactory.build(
            trip_date=date(2019, 11, 29), membership_required=True
        )

        # Even if they currently have no membership, we don't consider it requiring renewal
        # (If a trip is announced over a year in advance, requiring 'renewal'
        #  would prevent _any_ members from signing up)
        self.assertFalse(self._should_renew_for(future_trip, None))
        # Membership will expire before the trip, but we don't request renewal
        self.assertFalse(self._should_renew_for(future_trip, date(2019, 11, 28)))

    def test_normal_renewal(self):
        """In normal cases (upcoming trip, membership required) we require renewal."""
        # Trip takes place within the ~40 day window
        future_trip = TripFactory.build(
            trip_date=date(2019, 11, 25), membership_required=True
        )

        # Participants with no membership should renew
        self.assertTrue(self._should_renew_for(future_trip, None))
        # Participants with a membership expiring before the trip should renew
        self.assertTrue(self._should_renew_for(future_trip, date(2019, 11, 18)))
        # Participants with a membership expiring after the trip are cleared!
        self.assertFalse(self._should_renew_for(future_trip, date(2019, 11, 28)))
        self.assertFalse(self._should_renew_for(future_trip, date(2020, 10, 18)))
