import unittest
from datetime import date
from unittest import mock

import jwt
import requests
import responses
from django.test import SimpleTestCase, TestCase
from freezegun import freeze_time

from ws.tests import factories
from ws.utils import geardb


class JwtTest(unittest.TestCase):
    @freeze_time("Wed, 15 Jan 2020 14:45:00 EST")
    def test_sign_no_data(self):
        """Without a payload, we simple sign a token with an expiration."""
        with mock.patch.object(geardb, 'settings') as settings:
            settings.GEARDB_SECRET_KEY = 'sooper.secret'
            header = geardb.gear_bearer_jwt()

        name, content = header.split(' ')
        self.assertEqual(name, 'Bearer:')

        self.assertEqual(
            jwt.decode(content, 'sooper.secret', algorithms=['HS256']),
            {
                # Token expires 15 minutes in the future (as UTC timestamp)
                'exp': 1579118400,
            },
        )

    @freeze_time("Wed, 15 Jan 2020 14:45:00 EST")
    def test_sign_data_with_jwt(self):
        """The `gear_bearer_jwt()` method signs data for a 15-min period."""
        with mock.patch.object(geardb, 'settings') as settings:
            settings.GEARDB_SECRET_KEY = 'sooper.secret'
            header = geardb.gear_bearer_jwt(email='tim@mit.edu')

        name, content = header.split(' ')
        self.assertEqual(name, 'Bearer:')

        self.assertEqual(
            jwt.decode(content, 'sooper.secret', algorithms=['HS256']),
            {
                'email': 'tim@mit.edu',
                # Token expires 15 minutes in the future (as UTC timestamp)
                'exp': 1579118400,
            },
        )


class ApiTest(SimpleTestCase):
    @responses.activate
    def test_bad_status_code(self):
        responses.get(
            url="https://mitoc-gear.mit.edu/credentials",
            status=404,
        )
        with self.assertRaises(requests.exceptions.HTTPError):
            geardb.query_api('/credentials', user='admin')

    @responses.activate
    @mock.patch.object(geardb, 'settings')
    def test_query_api(self, settings):
        settings.GEARDB_SECRET_KEY = 'sooper.secret'

        responses.get(
            url="https://mitoc-gear.mit.edu/credentials",
            json={
                "count": 1,
                "next": None,
                "previous": None,
                "results": [{'user': 'admin', 'password': 'plaintext.auth.rules'}],
            },
            status=200,
        )

        results = geardb.query_api('/credentials', user='admin')

        self.assertEqual(
            results, [{'user': 'admin', 'password': 'plaintext.auth.rules'}]
        )

    @responses.activate
    def test_pagination_not_handled(self):
        """At present, we don't handle any pagination of results."""
        responses.get(
            url="https://mitoc-gear.mit.edu/api-auth/v1/credentials",
            json={
                "count": 10,
                "next": 'https://mitoc-gear.mit.edu/api-auth/v1/credentials?page=2',
                "previous": None,
                "results": [{'user': 'admin', 'password': 'plaintext.auth.rules'}],
            },
            status=200,
        )

        with mock.patch.object(geardb.logger, 'error') as log_error:
            results = geardb.query_api('/api-auth/v1/credentials')
        self.assertEqual(
            results, [{'user': 'admin', 'password': 'plaintext.auth.rules'}]
        )
        log_error.assert_called_once_with(
            "Results are paginated; this is not expected or handled. (%s / %s results), URL: %s, Next: %s",
            1,
            10,
            'https://mitoc-gear.mit.edu/api-auth/v1/credentials',
            'https://mitoc-gear.mit.edu/api-auth/v1/credentials?page=2',
        )


class UpdateAffiliationTest(TestCase):
    def test_old_student_status(self):
        participant = factories.ParticipantFactory.create(affiliation='S')

        with responses.RequestsMock():
            response = geardb.update_affiliation(participant)
        self.assertIsNone(response)

    @responses.activate
    def test_reports_affiliation(self):
        """We report affiliation for a simple user with just one email."""
        participant = factories.ParticipantFactory.create(
            affiliation='NA', email='tim@mit.edu'
        )

        responses.put(
            'https://mitoc-gear.mit.edu/api-auth/v1/affiliation/',
            match=[
                responses.matchers.json_params_matcher(
                    {
                        'email': 'tim@mit.edu',
                        'affiliation': 'NA',
                        'other_verified_emails': [],
                    }
                )
            ],
        )

        geardb.update_affiliation(participant)

    @staticmethod
    def test_reports_affiliation_with_other_emails():
        """We report all known verified emails."""
        tim = factories.ParticipantFactory.create(affiliation='NA', email='tim@mit.edu')

        factories.EmailFactory.create(
            user_id=tim.user_id,
            verified=False,
            primary=False,
            # Tim clearly doesn't own this email
            email='tim@whitehouse.gov',
        )
        for verified_email in ['tim@example.com', 'tim+two@mit.edu']:
            factories.EmailFactory.create(
                user_id=tim.user_id, verified=True, primary=False, email=verified_email
            )

        responses.put(
            'https://mitoc-gear.mit.edu/api-auth/v1/affiliation/',
            match=[
                responses.matchers.json_params_matcher(
                    {
                        'email': 'tim@mit.edu',
                        'affiliation': 'NA',
                        'other_verified_emails': ['tim+two@mit.edu', 'tim@example.com'],
                    }
                )
            ],
        )

        geardb.update_affiliation(tim)


class QueryGearDBForMembershipTest(TestCase):
    def test_user_without_any_emails(self):
        """We don't bother hitting the API if missing verified emails to use.

        (in practice, this should not happen - only participants can
        use the API route which hits this helper).
        """
        user = factories.UserFactory(emailaddress__verified=False)
        with responses.RequestsMock():  # (No API calls made)
            membership = geardb.query_geardb_for_membership(user)
        self.assertIsNone(membership)

    @responses.activate
    def test_no_results(self):
        """Test our handling of an empty `results` list.

        (I don't think this presently happens, but it's good to check)
        """
        user = factories.UserFactory(email='timothy@mit.edu')
        responses.get(
            url='https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email=timothy@mit.edu',
            json={
                "count": 0,
                "next": None,
                "previous": None,
                "results": [],
            },
        )

        membership = geardb.query_geardb_for_membership(user)
        self.assertEqual(
            membership,
            geardb.MembershipWaiver(
                email=None,
                membership_expires=None,
                waiver_expires=None,
            ),
        )

    @responses.activate
    def test_no_membership_found(self):
        user = factories.UserFactory(email='timothy@mit.edu')
        responses.get(
            url='https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email=timothy@mit.edu',
            json={
                "count": 0,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "email": "",
                        "alternate_emails": [],
                        "membership": {},
                        "waiver": {},
                    }
                ],
            },
        )

        membership = geardb.query_geardb_for_membership(user)
        self.assertEqual(
            membership,
            geardb.MembershipWaiver(
                email=None,
                membership_expires=None,
                waiver_expires=None,
            ),
        )

    @responses.activate
    @freeze_time('2022-07-11 22:00 EDT')
    def test_success(self):
        user = factories.UserFactory(email='bob@mit.edu')
        factories.EmailFactory(email='robert@mit.edu', verified=True, user=user)
        responses.get(
            url='https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email=bob@mit.edu&email=robert@mit.edu',
            json={
                "count": 0,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "email": "robert@mit.edu",
                        "alternate_emails": ["bob@mit.edu"],
                        "membership": {
                            "membership_type": "NA",
                            "expires": "2023-05-05",
                        },
                        "waiver": {"expires": "2023-05-04"},
                    }
                ],
            },
        )

        membership = geardb.query_geardb_for_membership(user)
        self.assertEqual(
            membership,
            geardb.MembershipWaiver(
                email='robert@mit.edu',
                membership_expires=date(2023, 5, 5),
                waiver_expires=date(2023, 5, 4),
            ),
        )


class MembershipStatsTest(TestCase):
    """Small stub class, to be completed once a full API integration returns."""

    def test_currently_empty(self):
        """We can at least *call* this method, it just returns nothing for now."""
        self.assertEqual(geardb.membership_information(), {})
