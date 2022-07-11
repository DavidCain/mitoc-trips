import unittest
from unittest import mock

import jwt
import requests
import responses
from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase
from freezegun import freeze_time

from ws.tests import TestCase, factories
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
            url="https://mitoc-gear.mit.edu/credentials",
            json={
                "count": 10,
                "next": 'https://mitoc-gear.mit.edu/api-auth/v1/credentials?page=2',
                "previous": None,
                "results": [{'user': 'admin', 'password': 'plaintext.auth.rules'}],
            },
            status=200,
        )

        with mock.patch.object(geardb.logger, 'error') as log_error:
            results = geardb.query_api('/credentials', user='admin')
        self.assertEqual(
            results, [{'user': 'admin', 'password': 'plaintext.auth.rules'}]
        )
        log_error.assert_called_once_with(
            "Results are paginated; this is not expected or handled."
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


class NoUserTests(SimpleTestCase):
    """Convenience methods neatly handle missing or anonymous users."""

    def test_expiration_no_emails(self):
        """Test users with no email addresses."""
        self.assertIsNone(geardb.user_membership_expiration(None))
        self.assertIsNone(geardb.user_membership_expiration(AnonymousUser()))

    def test_verified_email_no_user(self):
        """Test users with no email addresses."""
        self.assertEqual(geardb.verified_emails(AnonymousUser()), [])
        self.assertEqual(geardb.verified_emails(None), [])
