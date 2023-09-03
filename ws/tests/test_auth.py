import unittest.mock
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from ws.tests import factories
from ws.tests.helpers import PermHelpers

login_required_routes = [
    'all_trips_medical',
    'account_change_password',
    #'manage_applications',
    #'manage_trips',
    'participant_lookup',
    'trip_signup',
    'leader_trip_signup',
    'discounts',
    'lottery_preferences',
    'lottery_pairing',
]


class AuthTests(TestCase):
    """Test user authentication and authorization.

    These tests hit a lot of major routes in checking our access control system,
    but this is not meant as an exhaustive test of all available routes. Rather,
    it's supposed to test the authorization mechanisms themselves.

    There are a few levels of authorization in the app:
     - anonymous:
         can view some public-facing pages
     - authenticated:
         those with user accounts, but who may not have not supplied necessary
         medical information. They essentially have the same browsing
         privileges as anonymous users until completing the participant form.
     - participants:
         anyone who has filled out the participation form includes leaders,
         admins, activity chairs (i.e. everyone)
     - privileged participants:
         privileges are based on groups. Some participants belong to the
         leaders group, others are activity chairs
    """

    user: ClassVar[User]

    @classmethod
    def setUpTestData(cls):
        cls.user = factories.UserFactory.create(
            email='fake@example.com',
            password='password',  # noqa: S106
        )

    def login(self):
        return self.client.login(
            email=self.user.email,
            password='password',  # noqa: S106
        )

    def assertProfileRedirectedTo(self, response, desired_page):  # noqa: N802
        """Check for edit profile redirect on a given response."""
        self.assertEqual(response.status_code, 302)

        parsed = urlparse(response.url)
        self.assertEqual(parsed.path, reverse('edit_profile'))
        qs = parse_qs(parsed.query)
        self.assertEqual(qs['next'], [desired_page])

    def test_open_pages(self):
        """Anonymous users can browse a number of pages."""
        for open_url in [
            'contact',
            'help-home',
            'help-about',
            'help-personal_info',
            'help-lottery',
            'help-signups',
            'upcoming_trips',
            'stats',
        ]:
            response = self.client.get(reverse(open_url))
            self.assertEqual(response.status_code, 200)

    def test_viewing_trips(self):
        """Anonymous users can view trips (they just can't sign up)."""
        trip = factories.TripFactory.create()
        view_trip = self.client.get(reverse('view_trip', kwargs={'pk': trip.pk}))
        self.assertEqual(view_trip.status_code, 200)

    def test_unregistered_participant_pages(self):
        """Unregistered users are prompted to log in on restricted pages."""
        # Non-exhaustive list of restricted URLs (some require more than login)
        for login_required in login_required_routes:
            response = self.client.get(reverse(login_required))
            self.assertEqual(response.status_code, 302)
            self.assertIn('login', response.url)

    def test_registered_participant_pages(self):
        """Registered users will be redirected on participant-only pages."""
        desired_page = reverse('all_trips_medical')
        self.login()
        response = self.client.get(desired_page)
        self.assertProfileRedirectedTo(response, desired_page)

    @unittest.mock.patch('ws.decorators.profile_needs_update')
    def test_participant_pages(self, profile_needs_update):
        """Participants are allowed to view certain pages."""
        par_only_page = reverse('discounts')
        self.login()

        # When authenticated, but not a participant: redirected to edit profile
        no_par_response = self.client.get(par_only_page)
        self.assertProfileRedirectedTo(no_par_response, par_only_page)

        PermHelpers.mark_participant(self.user)
        profile_needs_update.return_value = False

        # When authenticated and a participant: success
        par_response = self.client.get(par_only_page)
        self.assertEqual(par_response.status_code, 200)

    @unittest.mock.patch('ws.decorators.profile_needs_update')
    def test_leader_pages(self, profile_needs_update):
        """Participants are given forbidden messages on leader-only pages.

        Leaders are able to view these pages as normal.
        """
        self.login()

        # Membership in participant group is sufficient to validate participant
        # (Making profile_needs_update return False skips participant checks)
        PermHelpers.mark_participant(self.user)
        profile_needs_update.return_value = False

        # leader-only GET pages that don't require pks
        leader_pages = ['leaders', 'participant_lookup']

        # HTTP Forbidden on leader pages without group membership
        for leader_page in leader_pages:
            response = self.client.get(reverse(leader_page))
            self.assertEqual(response.status_code, 403)

        # HTTP OK when the user is marked as a leader
        PermHelpers.mark_leader(self.user)
        for leader_page in leader_pages:
            response = self.client.get(reverse(leader_page))
            self.assertEqual(response.status_code, 200)
