from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase

from ws.utils.dates import local_date
from ws.utils import geardb


class NoUserTests(SimpleTestCase):
    """ Convenience methods neatly handle missing or anonymous users. """
    def test_expiration_no_emails(self):
        """ Test users with no email addresses. """
        self.assertIsNone(geardb.user_membership_expiration(None))
        self.assertIsNone(geardb.user_membership_expiration(AnonymousUser()))

    def test_verified_email_no_user(self):
        """ Test users with no email addresses. """
        self.assertEqual(geardb.verified_emails(AnonymousUser()), [])
        self.assertEqual(geardb.verified_emails(None), [])


class MembershipFormattingTests(SimpleTestCase):
    email = 'foo@example.com'

    @classmethod
    def setUp(cls):
        """ Use some convenience dates.

        All we care about when testing is that the dates are in the past or the
        future. Create two of each so we can be sure the right date was put
        into the right part of the response.
        """
        cls.future = local_date() + timedelta(days=1)
        cls.future2 = local_date() + timedelta(days=2)
        cls.past = local_date() - timedelta(days=1)
        cls.past2 = local_date() - timedelta(days=2)

    def fmt(self, membership_expires=None, waiver_expires=None):
        return geardb.format_membership(
            self.email,
            membership_expires=membership_expires and getattr(self, membership_expires),
            waiver_expires=waiver_expires and getattr(self, waiver_expires)
        )

    def test_membership_formatting(self):
        """ Test formatting of a normal, non-expired membership. """
        formatted = self.fmt(membership_expires='future', waiver_expires='future2')
        expected = {
            'membership': {
                'expires': self.future,
                'active': True,
                'email': self.email
            },
            'waiver': {
                'expires': self.future2,
                'active': True
            },
            'status': 'Active'
        }
        self.assertEqual(formatted, expected)

    def test_expired(self):
        """ Check output when both membership and waiver expired. """
        formatted = self.fmt(membership_expires='past', waiver_expires='past2')
        expected = {
            'membership': {
                'expires': self.past,
                'active': False,
                'email': self.email
            },
            'waiver': {
                'expires': self.past2,
                'active': False
            },
            'status': 'Expired'
        }
        self.assertEqual(formatted, expected)

    def test_bad_waiver(self):
        """ Check output when membership is valid, but waiver is not. """
        # First, check an expired waiver
        formatted = self.fmt(membership_expires='future', waiver_expires='past')
        expected = {
            'membership': {
                'expires': self.future,
                'active': True,
                'email': self.email
            },
            'waiver': {
                'expires': self.past,
                'active': False
            },
            'status': 'Waiver Expired'
        }
        self.assertEqual(formatted, expected)

        # Then, check a missing waiver
        no_waiver = self.fmt(membership_expires='future', waiver_expires=None)
        expected['waiver']['expires'] = None
        expected['status'] = 'Missing Waiver'
        self.assertEqual(no_waiver, expected)

    def test_bad_membership(self):
        """ Check output when waiver is valid, but membership is not. """
        # First, check an expired membership
        formatted = self.fmt(membership_expires='past', waiver_expires='future')
        expected = {
            'membership': {
                'expires': self.past,
                'active': False,
                'email': self.email
            },
            'waiver': {
                'expires': self.future,
                'active': True
            },
            'status': 'Missing Membership'
        }
        self.assertEqual(formatted, expected)

        # Then, check a missing membership
        # (Also reported as 'Missing Membership')
        missing = self.fmt(membership_expires=None, waiver_expires='future')
        expected['membership']['expires'] = None
        self.assertEqual(missing, expected)
