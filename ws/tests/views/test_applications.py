from bs4 import BeautifulSoup
from django.contrib.auth.models import Group
from django.test import Client
from freezegun import freeze_time

import ws.utils.dates as date_utils
from ws import enums
from ws.tests import TestCase, factories, strip_whitespace


class Helpers:
    client: Client

    def _get(self, url: str):
        response = self.client.get(url)
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, 'html.parser')
        return response, soup


class ClimbingLeaderApplicationTest(TestCase, Helpers):
    """Climbing leaders apply via a special Google Form."""

    BASE_FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSeWeIjtQ-p4mH_zGS-YvedvkbmVzBQOarIvzfzBzEgHMKuZzw'

    @staticmethod
    def _create_application_and_approve():
        application = factories.ClimbingLeaderApplicationFactory.create(
            # Note that the form logic usually handles this
            year=date_utils.local_date().year,
        )
        factories.LeaderRatingFactory.create(
            activity=enums.Activity.CLIMBING.value,
            participant=application.participant,
        )
        return application

    def setUp(self):
        self.participant = factories.ParticipantFactory.create(name='Tim Beaver')
        self.client.force_login(self.participant.user)

    def test_climbing_application_via_google_form(self):
        _response, soup = self._get('/climbing/leaders/apply/')

        # For clients on tablets or larger, we embed a form
        soup.find(
            'iframe',
            attrs={
                'class': 'hidden-sm',
                # Form is embedded, pre-filled with participant's name
                'src': f'{self.BASE_FORM_URL}/viewform?embedded=true&entry.1371106720=Tim+Beaver',
            },
        )

        # We link straight to the form, for those on mobile (or who prefer to not use embedded)
        soup.find(
            'a',
            attrs={
                'href': f'{self.BASE_FORM_URL}/viewform?entry.1371106720=Tim+Beaver',
            },
        )

        # Page also includes our general description on climbing ratings
        help_section_start = soup.find('h3')
        self.assertEqual(help_section_start.text, 'For all climbing leaders:')
        self.assertEqual(
            help_section_start.find_next('li').text,
            'You have strong group management skills.',
        )

    def test_submission_blocked(self):
        """Even though the ClimbingLeaderApplication model exists, you can't apply."""
        resp = self.client.post(
            '/climbing/leaders.apply',
            {'outdoor_sport_leading_grade': '5.11d'},
        )
        self.assertEqual(resp.status_code, 404)

    def test_old_applications_climbing(self):
        with freeze_time("2018-08-13 18:45 EDT"):
            self._create_application_and_approve()
        with freeze_time("2019-06-22 12:23 EDT"):
            self._create_application_and_approve()

        # make_chair(self.participant.user, Activity.CLIMBING)
        Group.objects.get(name='climbing_chair').user_set.add(self.participant.user)
        _response, soup = self._get('/climbing/applications/')
        self.assertEqual(
            soup.find('p').text,
            'Only archived climbing leader applications appear here.',
        )
        self.assertEqual(
            [h2.text for h2 in soup.find_all('h2')],
            [
                'Leader Applications',
                'Past Applications - 2019',
                'Past Applications - 2018',
            ],
        )

    def test_no_applications_climbing(self):
        # make_chair(self.participant.user, Activity.CLIMBING)
        Group.objects.get(name='climbing_chair').user_set.add(self.participant.user)
        _response, soup = self._get('/climbing/applications/')

        self.assertEqual(
            soup.find('p').text,
            'Only archived climbing leader applications appear here.',
        )


class HikingLeaderApplicationTest(TestCase, Helpers):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_preamble(self):
        _response, soup = self._get('/hiking/leaders/apply/')
        self.assertEqual(
            strip_whitespace(soup.find('h1').text), 'Hiking Leader Application'
        )
        self.assertEqual(
            soup.find('p').text,
            "Please complete and submit the form below if you're interested in becoming a MITOC Hiking Leader.",
        )

    def test_key_fields_hidden(self):
        _response, soup = self._get('/climbing/leaders/apply/')
        # The year is automatically added by the server.
        self.assertFalse(soup.find('input', attrs={'name': 'year'}))
        # The participant is given by the session, and added to the form by the server.
        self.assertFalse(soup.find('input', attrs={'name': 'participant'}))
        # Previous rating is provided by the system.
        self.assertFalse(soup.find('input', attrs={'name': 'previous_rating'}))


@freeze_time("2020-10-20 14:56:00 EST")
class WinterSchoolLeaderApplicationTest(TestCase, Helpers):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_title(self):
        _response, soup = self._get('/winter_school/leaders/apply/')
        self.assertEqual(
            strip_whitespace(soup.find('h1').text),
            'Winter School 2021 Leader Application',
        )


class AllLeaderApplicationsRecommendationTest(TestCase, Helpers):
    """Tests for the 'needs recommendation' vs. 'needs rating' mechanism."""

    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_0_activity_chairs(self):
        self.participant.user.is_superuser = True
        self.participant.user.save()
        self.assertFalse(Group.objects.get(name='hiking_chair').user_set.exists())

        application = factories.HikingLeaderApplicationFactory.create()
        response, soup = self._get('/hiking/applications/')

        # There are no chairs. Thus, the application needs no recommendation, just a rating.
        self.assertEqual(response.context_data['needs_rec'], [])
        self.assertEqual(response.context_data['needs_rating'], [application])

        self.assertEqual(
            strip_whitespace(soup.find('div', attrs={'class': 'alert-info'}).text),
            "When there are multiple activity chairs, co-chairs can make recommendations to one another. "
            "However, this doesn't really make sense when there is not an acting chair.",
        )

    def test_1_activity_chair(self):
        Group.objects.get(name='hiking_chair').user_set.set([self.participant.user])

        application = factories.HikingLeaderApplicationFactory.create()
        response, soup = self._get('/hiking/applications/')

        self.assertEqual(response.context_data['needs_rec'], [])
        self.assertEqual(response.context_data['needs_rating'], [application])

        self.assertEqual(
            strip_whitespace(soup.find('div', attrs={'class': 'alert-info'}).text),
            "When there are multiple activity chairs, co-chairs can make recommendations to one another. "
            "However, this doesn't really make sense when there's a single chair.",
        )

    def test_2_activity_chairs(self):
        Group.objects.get(name='hiking_chair').user_set.set(
            [self.participant.user, factories.ParticipantFactory.create().user]
        )

        # Neither chair have recommended one application
        no_recs_application = factories.HikingLeaderApplicationFactory.create()

        response_1, soup_1 = self._get('/hiking/applications/')
        self.assertEqual(response_1.context_data['needs_rec'], [no_recs_application])
        self.assertEqual(response_1.context_data['needs_rating'], [])
        self.assertEqual(
            strip_whitespace(soup_1.find('div', attrs={'class', 'alert-info'}).text),
            'Recommend some leader ratings for other applications to populate this list.',
        )

        # Viewing chair gave a recommendation for one application
        one_rec_application = factories.HikingLeaderApplicationFactory.create()
        factories.LeaderRecommendationFactory.create(
            creator=self.participant,
            participant=one_rec_application.participant,
            activity=enums.Activity.HIKING.value,
        )

        response, soup = self._get('/hiking/applications/')
        self.assertEqual(response.context_data['needs_rec'], [no_recs_application])
        self.assertEqual(response.context_data['needs_rating'], [one_rec_application])
        self.assertIsNone(soup.find('div', attrs={'class', 'alert-info'}))


class AllLeaderApplicationsTest(TestCase, Helpers):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    @staticmethod
    def _create_application_and_approve():
        application = factories.HikingLeaderApplicationFactory.create(
            # Note that the form logic usually handles this
            year=date_utils.local_date().year,
        )
        factories.LeaderRatingFactory.create(
            activity=enums.Activity.HIKING.value, participant=application.participant
        )
        return application

    def test_no_applications(self):
        Group.objects.get(name='hiking_chair').user_set.add(self.participant.user)
        _response, soup = self._get('/hiking/applications/')
        self.assertEqual(
            soup.find('p').text, 'There are no leader applications pending your review.'
        )

    def test_only_approved_applications(self):
        Group.objects.get(name='hiking_chair').user_set.add(self.participant.user)
        with freeze_time("2018-08-13 18:45 EDT"):
            self._create_application_and_approve()

        _response, soup = self._get('/hiking/applications/')
        self.assertEqual(
            soup.find('p').text, 'There are no leader applications pending your review.'
        )
        self.assertEqual(
            [h2.text for h2 in soup.find_all('h2')],
            [
                'Leader Applications',
                'Past Applications - 2018',
            ],
        )

    def test_no_form_defined(self):
        Group.objects.get(name='boating_chair').user_set.add(self.participant.user)

        _response, soup = self._get('/boating/applications/')
        self.assertEqual(
            soup.find('p').text, 'There are no leader applications pending your review.'
        )
        self.assertIn(
            "You don't have any application form defined for Boating!",
            soup.find('div', attrs={'class': 'alert-warning'}).text,
        )
