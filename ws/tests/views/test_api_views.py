import time
from unittest import mock

import jwt
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, settings
from ws.tests import TestCase, factories


class JWTSecurityTest(TestCase):
    def test_bad_secret_denied(self):
        """Tokens signed with the wrong secret should be denied for obvious reasons."""
        year_2525 = 17514144000
        token = jwt.encode(
            {'exp': year_2525, 'email': 'tim@mit.edu'},
            algorithm='HS256',
            key='this is definitely not the real secret',
        )
        response = self.client.get(
            '/data/verified_emails/', HTTP_AUTHORIZATION=f'Bearer: {token}'
        )
        self.assertEqual(response.status_code, 401)

    @freeze_time("2019-02-22 12:25:00 EST")
    def test_expired_token_denied(self):
        """Expired tokens must not work."""
        token = jwt.encode(
            {'exp': int(time.time()) - 1, 'email': 'tim@mit.edu'},
            algorithm='HS256',
            key='this is definitely not the real secret',
        )
        response = self.client.get(
            '/data/verified_emails/', HTTP_AUTHORIZATION=f'Bearer: {token}'
        )
        self.assertEqual(response.status_code, 401)

    def test_real_secret_works(self):
        """First, we show that requests using a signed, non-expired token work."""
        year_2525 = 17514144000
        real_token = jwt.encode(
            {'exp': year_2525, 'email': 'tim@mit.edu'},
            algorithm='HS256',
            key=settings.MEMBERSHIP_SECRET_KEY,
        )
        response = self.client.get(
            '/data/verified_emails/', HTTP_AUTHORIZATION=f'Bearer: {real_token}'
        )
        self.assertEqual(response.status_code, 200)

    def test_real_secret_works_with_different_algorithm(self):
        """We also support HMAC with SHA-512."""
        year_2525 = 17514144000
        real_token = jwt.encode(
            {'exp': year_2525, 'email': 'tim@mit.edu'},
            algorithm='HS512',
            key=settings.MEMBERSHIP_SECRET_KEY,
        )
        response = self.client.get(
            '/data/verified_emails/', HTTP_AUTHORIZATION=f'Bearer: {real_token}'
        )
        self.assertEqual(response.status_code, 200)

    def test_disallowed_algorithm(self):
        """A token signed with the correct secret but the wrong algorithm is denied."""
        year_2525 = 17514144000
        real_token = jwt.encode(
            {'exp': year_2525, 'email': 'tim@mit.edu'},
            algorithm='HS384',
            key=settings.MEMBERSHIP_SECRET_KEY,
        )
        response = self.client.get(
            '/data/verified_emails/', HTTP_AUTHORIZATION=f'Bearer: {real_token}'
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {'message': 'invalid algorithm'})

    def test_attempted_attack_fails(self):
        """Assert that we *always* require a token signed with the secret.

        The special `none` algorithm in the JWT spec allows attackers to request
        data using a JWT which is not actually signed using a secret. If an API
        decodes tokens and allows the `none` algorithm, then that means it can
        grant access to attackers. This is bad.

        For more, see:
        https://auth0.com/blog/critical-vulnerabilities-in-json-web-token-libraries/
        """
        year_2525 = 17514144000

        malicious_token = jwt.encode(
            {'exp': year_2525, 'email': 'tim@mit.edu'}, algorithm='none', key=None
        )
        response = self.client.get(
            '/data/verified_emails/', HTTP_AUTHORIZATION=f'Bearer: {malicious_token}'
        )
        # Because the attacker gave a token without signing the secret, they get a 401
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {'message': 'invalid algorithm'})


class OtherVerifiedEmailsTest(TestCase):
    """We report what we know about a MITOCer to authenticated APIS."""

    def _query_for(self, email: str):
        real_token = jwt.encode(
            {'exp': time.time() + 60, 'email': email},
            algorithm='HS512',
            key=settings.MEMBERSHIP_SECRET_KEY,
        )
        return self.client.get(
            '/data/verified_emails/', HTTP_AUTHORIZATION=f'Bearer: {real_token}'
        )

    def test_unknown_user(self):
        """We just report back the same email if we don't find a match."""
        response = self._query_for('barry.o@whitehouse.gov')
        self.assertEqual(
            response.json(),
            {
                'name': None,
                'primary': 'barry.o@whitehouse.gov',
                'emails': ['barry.o@whitehouse.gov'],
            },
        )

    def test_normal_participant(self):
        """We handle the case of a participant with some verified & unverified emails."""
        tim = factories.ParticipantFactory.create(
            name='Tim Beaver', email='tim@example.com'
        )

        factories.EmailFactory.create(
            user_id=tim.user_id,
            verified=False,
            primary=False,
            # Tim clearly doesn't own this email
            email='tim@whitehouse.gov',
        )
        factories.EmailFactory.create(
            user_id=tim.user_id, verified=True, primary=False, email='tim@mit.edu'
        )

        response = self._query_for('tim@mit.edu')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'name': 'Tim Beaver',
                'primary': 'tim@example.com',
                'emails': ['tim@example.com', 'tim@mit.edu'],
            },
        )
        # We get the same result when querying under a different known email!
        self.assertEqual(response.json(), self._query_for('tim@example.com').json())

    def test_user_without_participant(self):
        """We handle the case of a user who never completed a participant record."""

        factories.UserFactory.create(email='tim@mit.edu')
        response = self._query_for('tim@mit.edu')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                'name': None,
                'primary': 'tim@mit.edu',
                'emails': ['tim@mit.edu'],
            },
        )


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

    def test_open_program(self):
        """Any active leader is allowed for an open program."""
        factories.LeaderRatingFactory.create(
            rating='Inactive', activity=enums.Activity.BIKING.value, active=False
        )
        h = factories.LeaderRatingFactory.create(
            participant__name='Hiker',
            rating='Leader',
            activity=enums.Activity.HIKING.value,
        )
        c = factories.LeaderRatingFactory.create(
            participant__name='Climber',
            rating='Sport',
            activity=enums.Activity.CLIMBING.value,
        )
        # Climbing leader is also a leader on a different activity!
        # (they will not be counted twice)
        factories.LeaderRatingFactory.create(
            participant=c.participant,
            rating='Downhill',
            activity=enums.Activity.BIKING.value,
        )

        response = self.client.get('/programs/circus/leaders.json')
        self.assertEqual(
            response.json(),
            {
                'leaders': [
                    {'id': c.participant_id, 'name': 'Climber', 'rating': None},
                    {'id': h.participant_id, 'name': 'Hiker', 'rating': None},
                ]
            },
        )

    def test_alphabetical(self):
        """Leaders are sorted by name."""
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
        """If, somehow multiple active ratings exist, we don't duplicate!"""
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


class JsonParticipantsTest(TestCase):
    def setUp(self):
        super().setUp()
        self.participant = factories.ParticipantFactory.create(
            name="Mr. Bolton", email="michael@example.com"
        )
        self.client.force_login(self.participant.user)

    def test_just_user(self):
        user = factories.UserFactory.create()
        self.client.force_login(user)
        response = self.client.get('/participants.json')
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get('/participants.json')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/?next=/participants.json")

    @staticmethod
    def _expect(par):
        return {
            'id': par.pk,
            'name': par.name,
            'email': par.email,
            'avatar': mock.ANY,  # (we test elsewhere)
        }

    def test_search(self):
        michaela = factories.ParticipantFactory.create(name="Michaela the MITOCer")
        michele = factories.ParticipantFactory.create(name="Michele da Italia")
        miguel = factories.ParticipantFactory.create(name="Miguel Michele")
        factories.ParticipantFactory.create(name="Aaron Blake")

        searcher = {
            'id': self.participant.pk,
            'name': 'Mr. Bolton',
            'email': 'michael@example.com',  # Match was on email, not name
            'avatar': 'https://www.gravatar.com/avatar/03ea78c0884c9ac0f73e6af7b9649e90?d=mm&s=200&r=pg',
        }

        others = [self._expect(michaela), self._expect(michele), self._expect(miguel)]

        # Search for something nobody will match on.
        response = self.client.get('/participants.json?search=Michelada')
        self.assertEqual(response.json(), {'participants': []})

        # Search everybody matching 'mich' (matches all but Aaron)
        response = self.client.get('/participants.json?search=Mich')
        matches = response.json()['participants']
        # TODO: Once using FTS or something, assert order.
        # For now, we just return in any given order.
        self.assertCountEqual(matches, [searcher, *others])

        # Exclude self when searching
        response = self.client.get('/participants.json?search=Mich&exclude_self=1')
        no_self_matches = response.json()['participants']
        self.assertCountEqual(no_self_matches, others)

    def test_exact_id(self):
        """Participants can be queried by an exact ID."""
        one = factories.ParticipantFactory.create()
        two = factories.ParticipantFactory.create()
        factories.ParticipantFactory.create()

        response = self.client.get(f'/participants.json?id={one.pk}&id={two.pk}')
        self.assertEqual(
            response.json(), {'participants': [self._expect(one), self._expect(two)]}
        )


class ApproveTripViewTest(TestCase):
    def setUp(self):
        super().setUp()
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def _approve(self, trip, approved=True):
        return self.client.post(
            f'/trips/{trip.pk}/approve/',
            {'approved': approved},
            content_type='application/json',
        )

    def test_unknown_activity(self):
        trip = factories.TripFactory.create(program=enums.Program.CIRCUS.value)
        response = self._approve(trip)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {'message': 'No chair for Circus'})

    def test_wrong_chair(self):
        trip = factories.TripFactory.create(
            program=enums.Program.WINTER_SCHOOL.value, chair_approved=False
        )
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        response = self._approve(trip)
        self.assertEqual(response.status_code, 403)

        trip.refresh_from_db()
        self.assertFalse(trip.chair_approved)

    def test_approve(self):
        trip = factories.TripFactory.create(
            program=enums.Program.WINTER_SCHOOL.value, chair_approved=False
        )
        perm_utils.make_chair(self.user, enums.Activity.WINTER_SCHOOL)
        response = self._approve(trip)
        self.assertEqual(response.status_code, 200)

        trip.refresh_from_db()
        self.assertTrue(trip.chair_approved)

        self._approve(trip, approved=False)
        trip.refresh_from_db()
        self.assertFalse(trip.chair_approved)
