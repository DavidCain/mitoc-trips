from collections import OrderedDict
from datetime import date, timedelta
import unittest.mock

from django.contrib.auth.models import AnonymousUser
from django.db import connections
from django.test import SimpleTestCase, TransactionTestCase

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


class MembershipExpirationTests(TransactionTestCase):
    @unittest.mock.patch('ws.utils.geardb.matching_memberships')
    def test_split_membership(self, matching_memberships):
        """ We handle a membership and waiver split across two emails. """
        memberships_by_email = {
            'active_waiver@example.com': {
                'membership': {'expires': None, 'active': False,
                               'email': 'active_waiver@example.com'},
                'waiver': {'expires': date(2019, 6, 12), 'active': True},
                'status': 'Missing Membership'
            },
            'active_membership@example.com': {
                'membership': {'expires': date(2019, 1, 5), 'active': True,
                               'email': 'active_membership@example.com'},
                'waiver': {'expires': None, 'active': False},
                'status': 'Missing Waiver'
            }
        }

        # All else held equal, most recent memberships are returned first
        matching_memberships.return_value = memberships_by_email
        self.assertEqual(geardb.membership_expiration(list(memberships_by_email)),
                         memberships_by_email['active_membership@example.com'])

    @unittest.mock.patch('ws.utils.geardb.matching_memberships')
    def test_newest_waiver_taken(self, matching_memberships):
        """ If an old membership has an active waiver, use it! """
        one_month_later = local_date() + timedelta(days=30)
        memberships_by_email = {
            '1@example.com': {
                'membership': {'expires': date(2011, 1, 1), 'active': False, 'email': '1@example.com'},
                'waiver': {'expires': None, 'active': False},
                'status': 'Expired'
            },
            '2@example.com': {
                'membership': {'expires': date(2012, 2, 2), 'active': False, 'email': '2@example.com'},
                'waiver': {'expires': None, 'active': False},
                'status': 'Expired'
            },
            '3@example.com': {
                'membership': {'expires': date(2013, 3, 3), 'active': False, 'email': '3@example.com'},
                'waiver': {'expires': None, 'active': False},
                'status': 'Expired'
            },
        }
        matching_memberships.return_value = memberships_by_email

        # All waivers are expired or missing, so we take the newest membership
        self.assertEqual(geardb.membership_expiration(list(memberships_by_email)),
                         memberships_by_email['3@example.com'])

        # Give the middle membership an active waiver, even though it's not the newest
        middle = memberships_by_email['2@example.com']
        middle['waiver'].update(expires=one_month_later, active=True)
        middle['status'] = 'Membership Expired'

        # '2@example.com' is not the newest membership, but it has an active waiver
        # (and all other memberships do not have an active waiver)
        self.assertEqual(geardb.membership_expiration(list(memberships_by_email)),
                         memberships_by_email['2@example.com'])


class MembershipSQLHelpers:
    def tearDown(self):
        """ Because of MySQL, each test's insertions aren't reverted. """
        with self.cursor as cursor:
            cursor.execute('delete from gear_peopleemails;')
            cursor.execute('delete from people_waivers;')
            cursor.execute('delete from people_memberships;')
            cursor.execute('delete from people;')

    @property
    def cursor(self):
        return connections['geardb'].cursor()

    @property
    def one_year_later(self):
        return local_date() + timedelta(days=365)

    def create_tim(self):
        with self.cursor as cursor:
            cursor.execute(
                '''
                insert into people (firstname, lastname, email, mitoc_credit, date_inserted)
                values (%(first)s, %(last)s, %(email)s, 0, now())
                ''', {'first': 'Tim', 'last': 'Beaver', 'email': 'tim@mit.edu'}
            )
            return cursor.lastrowid

    def record_alternate_email(self, person_id, email):
        with self.cursor as cursor:
            cursor.execute(
                '''
                insert into gear_peopleemails (person_id, alternate_email)
                values (%(person_id)s, %(email)s)
                ''', {'person_id': person_id, 'email': email}
            )
            return cursor.lastrowid

    def one_match(self, email):
        matches = geardb.matching_memberships([email])
        self.assertEqual(len(matches), 1)
        return matches[email]

    @property
    def just_tim(self):
        return self.one_match('tim@mit.edu')


class MembershipTests(MembershipSQLHelpers, TransactionTestCase):
    """ Test the underlying SQL that drives membership queries. """
    def test_no_people_record(self):
        """ Without a match, nothing is returned. """
        matches = geardb.matching_memberships(['not.in.database@example.com'])
        self.assertEqual(matches, OrderedDict())

    def test_no_membership_waiver(self):
        """ People records can still be returned without a membership or waiver. """
        self.create_tim()
        self.assertEqual(self.just_tim, {
            'membership': {'expires': None, 'active': False, 'email': 'tim@mit.edu'},
            'waiver': {'expires': None, 'active': False},
            'status': 'Expired'
        })

    def test_just_waiver(self):
        """ Participants can sign waivers without paying for a membership. """
        person_id = self.create_tim()
        with self.cursor as cursor:
            cursor.execute(
                '''
                insert into people_waivers (person_id, date_signed, expires)
                values (%(person_id)s, now(), %(expires)s)
                ''', {'person_id': person_id, 'expires': self.one_year_later}
            )
        self.assertEqual(self.just_tim, {
            'membership': {'expires': None, 'active': False, 'email': 'tim@mit.edu'},
            'waiver': {'expires': self.one_year_later, 'active': True},
            'status': 'Missing Membership'
        })

    def test_just_membership(self):
        """ Participants can have memberships without waivers. """
        person_id = self.create_tim()
        with self.cursor as cursor:
            cursor.execute(
                '''
                insert into people_memberships (
                  person_id, price_paid, membership_type, date_inserted, expires
                )
                values (%(person_id)s, 15, 'student', now(), %(expires)s)
                ''', {'person_id': person_id, 'expires': self.one_year_later}
            )
        self.assertEqual(self.just_tim, {
            'membership': {'expires': self.one_year_later, 'active': True, 'email': 'tim@mit.edu'},
            'waiver': {'expires': None, 'active': False},
            'status': 'Missing Waiver'
        })


class AlternateEmailTests(MembershipSQLHelpers, TransactionTestCase):
    def expect_under_email(self, email, lookup=None):
        expected = self.just_tim
        expected['membership']['email'] = email
        lookup_emails = lookup or [email]
        results = geardb.matching_memberships(lookup_emails)  # (OrderedDict)
        self.assertEqual({email: expected}, dict(results))

    def test_just_one_record(self):
        """ When requesting records under many emails, just one is returned.

        (Provided that the primary email is included in the lookup list)
        """
        person_id = self.create_tim()
        alternate_emails = [f'tim@{i}.example.com' for i in range(3)]
        for email in alternate_emails:
            self.record_alternate_email(person_id, email)

        # When we request just the alternate emails, it returns one for each
        self.assertEqual(len(geardb.matching_memberships(alternate_emails)), 3)

        # However, so long as the primary is included, we'll just have one
        all_emails = ['tim@mit.edu'] + alternate_emails
        self.expect_under_email('tim@mit.edu', lookup=all_emails)

    def test_alternate_email(self):
        """ We can look up participants by other emails. """
        person_id = self.create_tim()

        # First, there is no known membership for the other email
        self.assertEqual(geardb.matching_memberships(['tim@mitoc.org']),
                         OrderedDict())

        # Then, after tying the alternate email to the main account, results!
        self.record_alternate_email(person_id, 'tim@mitoc.org')
        self.expect_under_email('tim@mitoc.org')

        # Importantly, we can still look up by the main email address!
        self.expect_under_email('tim@mit.edu')

        # If looking up by both emails, the primary email is reported
        # (Importantly, only one membership is returned)
        self.expect_under_email('tim@mit.edu', lookup=['tim@mit.edu', 'tim@mitoc.org'])


class MembershipFormattingTests(SimpleTestCase):
    """ Test formatting of membership records, independent of the SQL. """
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
