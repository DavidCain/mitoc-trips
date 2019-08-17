from datetime import date

from django.test import SimpleTestCase
from freezegun import freeze_time

from ws import models


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
