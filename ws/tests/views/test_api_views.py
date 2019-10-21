from freezegun import freeze_time

from ws import enums
from ws.tests import TestCase, factories


class JsonProgramLeadersViewTest(TestCase):
    def setUp(self):
        super().setUp()
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get('/programs/climbing/leaders.json')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, "/accounts/login/?next=/programs/climbing/leaders.json"
        )

    def test_bad_program(self):
        response = self.client.get('/programs/snowmobiling/leaders.json')
        self.assertEqual(response.status_code, 404)

    def test_no_leaders(self):
        response = self.client.get('/programs/climbing/leaders.json')
        self.assertEqual(response.json(), {'leaders': []})

        factories.LeaderRatingFactory.create(activity=enums.Activity.HIKING.value)
        response = self.client.get('/programs/climbing/leaders.json')
        self.assertEqual(response.json(), {'leaders': []})

    def test_alphabetical(self):
        """ Leaders are sorted by name. """
        c = factories.LeaderRatingFactory.create(participant__name='Carl', rating='A')
        b = factories.LeaderRatingFactory.create(participant__name='Bob', rating='B')
        d = factories.LeaderRatingFactory.create(participant__name='Dee', rating='I')
        a = factories.LeaderRatingFactory.create(participant__name='Alice', rating='C')
        activity = a.activity_enum.value

        response = self.client.get(f'/programs/{activity}/leaders.json')
        self.assertEqual(
            response.json(),
            {
                'leaders': [
                    {'id': a.participant_id, 'name': 'Alice', 'rating': 'C'},
                    {'id': b.participant_id, 'name': 'Bob', 'rating': 'B'},
                    {'id': c.participant_id, 'name': 'Carl', 'rating': 'A'},
                    {'id': d.participant_id, 'name': 'Dee', 'rating': 'I'},
                ]
            },
        )

    def test_inactive_ratings_excluded(self):
        factories.LeaderRatingFactory.create(
            rating='Inactive', activity=enums.Activity.BIKING.value, active=False
        )

        # A participant with an old (inactive) rating only includes the active one
        jane = factories.ParticipantFactory.create(name='Jane Ng')
        factories.LeaderRatingFactory.create(
            rating='Co-leader',
            participant=jane,
            activity=enums.Activity.BIKING.value,
            active=False,
        )
        factories.LeaderRatingFactory.create(
            rating='Leader',
            participant=jane,
            activity=enums.Activity.BIKING.value,
            active=True,
        )
        response = self.client.get('/programs/biking/leaders.json')
        self.assertEqual(
            response.json(),
            {'leaders': [{'id': jane.pk, 'name': 'Jane Ng', 'rating': 'Leader'}]},
        )

    def test_latest_rating_taken(self):
        """ If, somehow multiple active ratings exist, we don't duplicate! """
        par = factories.ParticipantFactory.create(name='Steve O')

        with freeze_time("2019-02-22 12:25:00 EST"):
            factories.LeaderRatingFactory.create(
                rating='A',
                participant=par,
                activity=enums.Activity.WINTER_SCHOOL.value,
                active=True,
            )
        with freeze_time("2019-03-30 12:25:00 EST"):
            factories.LeaderRatingFactory.create(
                rating='B',
                participant=par,
                activity=enums.Activity.WINTER_SCHOOL.value,
                active=True,
            )
        with freeze_time("2019-04-04 12:25:00 EST"):
            factories.LeaderRatingFactory.create(
                rating='C',
                participant=par,
                activity=enums.Activity.WINTER_SCHOOL.value,
                active=True,
            )

        response = self.client.get('/programs/winter_school/leaders.json')
        self.assertEqual(
            response.json(),
            {'leaders': [{'id': par.pk, 'name': 'Steve O', 'rating': 'C'}]},
        )
