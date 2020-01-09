from bs4 import BeautifulSoup

import ws.utils.perms as perm_utils
from ws import enums, models
from ws.tests import TestCase, factories


class ManageLeadersViewTest(TestCase):
    def setUp(self):
        # Not actually chair!
        self.chair = factories.ParticipantFactory.create()
        self.client.force_login(self.chair.user)

        self.participant = factories.ParticipantFactory.create()

    def test_not_chair(self):
        response = self.client.get('/chair/leaders/')
        self.assertEqual(response.status_code, 403)

    def test_totally_invalid_activity(self):
        perm_utils.make_chair(self.chair.user, enums.Activity.CLIMBING)
        resp = self.client.post(
            '/chair/leaders/',
            {
                'participant': self.participant.pk,
                'activity': "Curling",
                'rating': "Curler",
                'notes': "Drinks with the best of 'em",
            },
        )
        self.assertFalse(resp.context['form'].is_valid())
        self.assertFalse(perm_utils.is_leader(self.participant.user))

    def test_create_ws_rating(self):
        perm_utils.make_chair(self.chair.user, enums.Activity.WINTER_SCHOOL)
        resp = self.client.post(
            '/chair/leaders/',
            {
                'participant': self.participant.pk,
                'activity': enums.Activity.WINTER_SCHOOL.value,
                'rating': "B coC",
                'notes': "",
            },
        )
        # We redirect back to the page
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/chair/leaders/')

        # The participant is now a WS leader, and we set the chair as the creator!
        self.assertTrue(perm_utils.is_leader(self.participant.user))
        rating = models.LeaderRating.objects.get(
            activity=enums.Activity.WINTER_SCHOOL.value, participant=self.participant
        )
        self.assertTrue(rating.active)
        self.assertEqual(rating.rating, "B coC")
        self.assertEqual(rating.creator, self.chair)

    def test_update_ws_rating(self):
        perm_utils.make_chair(self.chair.user, enums.Activity.WINTER_SCHOOL)
        factories.LeaderRatingFactory.create(
            participant=self.participant, rating="B coC", creator=self.chair,
        )

        resp = self.client.post(
            '/chair/leaders/',
            {
                'participant': self.participant.pk,
                'activity': enums.Activity.WINTER_SCHOOL.value,
                'rating': "C coI",
                'notes': "Upgraded!",
            },
        )
        # We redirect back to the page
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/chair/leaders/')

        # The participant has an upgrade now (& the old rating is inactive)
        rating = models.LeaderRating.objects.get(
            activity=enums.Activity.WINTER_SCHOOL.value,
            participant=self.participant,
            active=True,  # old rating is now inactive!
        )
        self.assertTrue(rating.active)
        self.assertEqual(rating.rating, "C coI")
        self.assertEqual(rating.creator, self.chair)


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
