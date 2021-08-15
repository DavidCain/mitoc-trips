from bs4 import BeautifulSoup
from django.contrib.auth.models import Group
from django.test import Client
from freezegun import freeze_time

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
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_preamble(self):
        _response, soup = self._get('/climbing/leaders/apply/')
        expected_preamble = (
            'Please fill out the form below to apply to become a climbing leader. '
            'In addition to this form, we require that applicants have '
            'two recommendations from current MITOC climbing leaders.'
        )
        self.assertEqual(
            strip_whitespace(soup.find('h1').text), 'Climbing Leader Application'
        )
        self.assertEqual(soup.find('p').text, expected_preamble)

    def test_key_fields_hidden(self):
        """With no default filter, we only show upcoming trips."""
        _response, soup = self._get('/climbing/leaders/apply/')
        # "Archived" is a value that's set by leaders on existing applications
        self.assertFalse(soup.find('input', attrs={'name': 'archived'}))
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
