from bs4 import BeautifulSoup

import ws.utils.perms as perm_utils
from ws import enums
from ws.tests import TestCase, factories


class AllLeadersViewTest(TestCase):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_anonymous_cannot_view(self):
        self.client.logout()
        response = self.client.get('/leaders/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/accounts/login/?next=/leaders/')

    def test_regular_participants_cannot_view(self):
        self.assertFalse(self.participant.is_leader)
        response = self.client.get('/leaders/')
        self.assertEqual(response.status_code, 403)

    def test_leaders_can_view(self):
        factories.LeaderRatingFactory.create(
            participant=self.participant, activity=enums.Activity.CLIMBING.value
        )
        other_leader_rating = factories.LeaderRatingFactory.create(
            activity=enums.Activity.CLIMBING.value
        )
        # Inactive leaders are not included!
        factories.LeaderRatingFactory.create(
            activity=enums.Activity.CLIMBING.value, active=False
        )

        response = self.client.get('/leaders/')
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            response.context['leaders'],
            [self.participant, other_leader_rating.participant],
        )
        self.assertEqual(
            response.context['activities'],
            [
                (enums.Activity.BIKING.value, 'Biking'),
                (enums.Activity.BOATING.value, 'Boating'),
                (enums.Activity.CLIMBING.value, 'Climbing'),
                (enums.Activity.HIKING.value, 'Hiking'),
                (enums.Activity.WINTER_SCHOOL.value, 'Winter School'),
            ],
        )


class ActivityLeadersViewTest(TestCase):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    def test_non_chairs_may_not_view(self):
        response = self.client.get('/climbing/leaders/')
        self.assertEqual(response.status_code, 403)

    def test_bad_activity(self):
        perm_utils.make_chair(self.participant.user, enums.Activity.CLIMBING)
        response = self.client.get('/snowmobiling/leaders/')
        self.assertEqual(response.status_code, 404)

    def test_no_active_leaders(self):
        perm_utils.make_chair(self.participant.user, enums.Activity.CLIMBING)
        response = self.client.get('/climbing/leaders/')
        self.assertEqual(response.context['activity_enum'], enums.Activity.CLIMBING)
        soup = BeautifulSoup(response.content, 'html.parser')
        self.assertTrue(soup.find('h2', text='Climbing Leaders'))
        self.assertTrue(soup.find('p', text='No active leaders!'))

    def test_active_leaders(self):
        rating = factories.LeaderRatingFactory.create(
            participant__name='Tommy Caldwell',
            activity=enums.Activity.CLIMBING.value,
            active=True,
        )
        # Inactive ratings won't be displayed
        factories.LeaderRatingFactory.create(
            participant__name='Alex Honnold',
            activity=enums.Activity.CLIMBING.value,
            active=False,
        )

        perm_utils.make_chair(self.participant.user, enums.Activity.CLIMBING)
        response = self.client.get('/climbing/leaders/')
        self.assertEqual(response.context['activity_enum'], enums.Activity.CLIMBING)
        soup = BeautifulSoup(response.content, 'html.parser')

        self.assertFalse(soup.find('table').find(text='Alex Honnold'))
        leader = soup.find('table').find('td', text='Tommy Caldwell')
        self.assertEqual(
            leader.find('a')['href'], f'/participants/{rating.participant_id}/'
        )
