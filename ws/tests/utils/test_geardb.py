import unittest
from unittest import mock

import jwt
import requests
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
    def test_bad_status_code(self):
        fake_response = mock.Mock(spec=requests.Response)
        fake_response.status_code = 404

        with mock.patch.object(requests, 'get') as fake_get:
            fake_get.return_value = fake_response
            with self.assertRaises(geardb.APIError):
                geardb.query_api('/credentials', user='admin')

    @mock.patch.object(geardb, 'settings')
    def test_query_api(self, settings):
        settings.GEARDB_SECRET_KEY = 'sooper.secret'

        fake_response = mock.Mock(spec=requests.Response)
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "count": 1,
            "next": None,
            "previous": None,
            "results": [{'user': 'admin', 'password': 'plaintext.auth.rules'}],
        }

        with mock.patch.object(requests, 'get') as fake_get:
            fake_get.return_value = fake_response
            results = geardb.query_api('/credentials', user='admin')
        self.assertEqual(
            results, [{'user': 'admin', 'password': 'plaintext.auth.rules'}]
        )

    def test_pagination_not_handled(self):
        """At present, we don't handle any pagination of results."""
        fake_response = mock.Mock(spec=requests.Response)
        fake_response.status_code = 200
        fake_response.json.return_value = {
            "count": 10,
            "next": 'https://mitoc-gear.mit.edu/api-auth/v1/credentials?page=2',
            "previous": None,
            "results": [{'user': 'admin', 'password': 'plaintext.auth.rules'}],
        }

        with mock.patch.object(requests, 'get') as fake_get:
            fake_get.return_value = fake_response
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

        with mock.patch.object(requests, 'put') as fake_put:
            response = geardb.update_affiliation(participant)
        self.assertIsNone(response)
        fake_put.assert_not_called()

    @staticmethod
    def test_reports_affiliation():
        """We report affiliation for a simple user with just one email."""
        participant = factories.ParticipantFactory.create(
            affiliation='NA', email='tim@mit.edu'
        )

        with mock.patch.object(requests, 'put') as fake_put:
            geardb.update_affiliation(participant)
        fake_put.assert_called_once_with(
            'https://mitoc-gear.mit.edu/api-auth/v1/affiliation/',
            headers={'Authorization': mock.ANY},
            json={
                'email': 'tim@mit.edu',
                'affiliation': 'NA',
                'other_verified_emails': [],
            },
        )

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

        with mock.patch.object(requests, 'put') as fake_put:
            geardb.update_affiliation(tim)
        fake_put.assert_called_once_with(
            'https://mitoc-gear.mit.edu/api-auth/v1/affiliation/',
            headers={'Authorization': mock.ANY},
            json={
                'email': 'tim@mit.edu',
                'affiliation': 'NA',
                'other_verified_emails': ['tim+two@mit.edu', 'tim@example.com'],
            },
        )


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
