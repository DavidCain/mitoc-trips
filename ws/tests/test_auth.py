from urllib.parse import urlparse, parse_qs

import mock

from django.contrib.auth.models import Group
from django.test import Client, TestCase
from django.urls import reverse

from ws import models


class AuthTests(TestCase):
    """ Test user authentication and authorization.

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
    fixtures = ['ws']

    def setUp(self):
        self.client = Client()

    @classmethod
    def setUpTestData(cls):
        cls.password = 'foobar'
        cls.user = models.User.objects.create_user(
            username='foo',
            email='foo@example.com',
            password=cls.password
        )

    def login(self):
        return self.client.login(email=self.user.email, password=self.password)

    def mark_leader(self):
        """ Mark the user as belonging to the leaders group.

        Note that some views may expect a LeaderRating to be present for the
        user's Participant object. This is sufficient to pass access control, though.
        """
        leaders, _ = Group.objects.get_or_create(name='leaders')
        leaders.user_set.add(self.user)

    def mark_participant(self):
        """ Mark the user as having participation information.

        Note that this may not be enough to allow access to participant-only
        pages. In the cases of bad phone numbers, non-verified emails, or any
        other state of dated participation info, users will still be rediricted
        to update their information.

        To disable this redirect, mock `ws.decorators.profile_needs_update`
        """
        users_with_info, _ = Group.objects.get_or_create(name='users_with_info')
        users_with_info.user_set.add(self.user)

    def assertProfileRedirectedTo(self, response, desired_page):
        """ Check for edit profile redirect on a given response. """
        self.assertEqual(response.status_code, 302)

        parsed = urlparse(response.url)
        self.assertEqual(parsed.path, reverse('edit_profile'))
        qs = parse_qs(parsed.query)
        self.assertEqual(qs['next'], [desired_page])

    def test_open_pages(self):
        """ Anonymous users can browse a number of pages. """
        for open_url in ['contact',
                         'help-home', 'help-about', 'help-personal_info',
                         'help-lottery', 'help-signups', 'help-leading_trips',
                         'all_trips', 'upcoming_trips',
                         'stats', 'json-trips_by_leader']:
            response = self.client.get(reverse(open_url))
            self.assertEqual(response.status_code, 200)

        trip = models.Trip.objects.first()
        view_trip = self.client.get(reverse('view_trip', kwargs={'pk': trip.pk}))
        self.assertEqual(view_trip.status_code, 200)

    def test_unregistered_participant_pages(self):
        """ Unregistered users are prompted to log in on restricted pages. """
        # Non-exhaustive list of restricted URLs (some require more than login)
        for login_required in ['all_trips_medical', 'account_change_password',
                               'manage_leaders',
                               'manage_applications', 'manage_trips',
                               'participant_lookup', 'json-membership_statuses',
                               'trip_signup', 'leader_trip_signup',
                               'discounts', 'lottery_preferences',
                               'lottery_pairing']:
            response = self.client.get(reverse(login_required))
            self.assertEqual(response.status_code, 302)
            self.assertIn('login', response.url)

    def test_registered_participant_pages(self):
        """ Registered users will be redirected on participant-only pages. """
        desired_page = reverse('all_trips_medical')
        self.login()
        response = self.client.get(desired_page)
        self.assertProfileRedirectedTo(response, desired_page)

    @mock.patch('ws.decorators.profile_needs_update')
    def test_participant_pages(self, profile_needs_update):
        """ Participants are allowed to view certain pages. """
        par_only_page = reverse('discounts')
        self.login()

        # When authenticated, but not a participant: redirected to edit profile
        no_par_response = self.client.get(par_only_page)
        self.assertProfileRedirectedTo(no_par_response, par_only_page)

        self.mark_participant()
        profile_needs_update.return_value = False

        # When authenticated and a participant: success
        par_response = self.client.get(par_only_page)
        self.assertEqual(par_response.status_code, 200)

    @mock.patch('ws.decorators.profile_needs_update')
    def test_leader_pages(self, profile_needs_update):
        """ Participants are given forbidden messages on leader-only pages.

        Leaders are able to view these pages as normal.
        """
        self.login()

        # Membership in participant group is sufficient to validate participant
        # (Making profile_needs_update return False skips participant checks)
        self.mark_participant()
        profile_needs_update.return_value = False

        # leader-only GET pages that don't require pks
        leader_pages = ['leaders', 'create_trip', 'participant_lookup']

        # HTTP Forbidden on leader pages without group membership
        for leader_page in leader_pages:
            response = self.client.get(reverse(leader_page))
            self.assertEqual(response.status_code, 403)

        # HTTP OK when the user is marked as a leader
        self.mark_leader()
        for leader_page in leader_pages:
            response = self.client.get(reverse(leader_page))
            self.assertEqual(response.status_code, 200)
