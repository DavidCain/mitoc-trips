import time
from unittest import mock

import jwt
import responses
from django.test import TestCase
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, models, settings, tasks
from ws.api_views import MemberInfo
from ws.tests import factories
from ws.utils import member_stats
from ws.utils.signups import add_to_waitlist


class JWTSecurityTest(TestCase):
    def test_bad_secret_denied(self):
        """Tokens signed with the wrong secret should be denied for obvious reasons."""
        year_2525 = 17514144000
        token = jwt.encode(
            {"exp": year_2525, "email": "tim@mit.edu"},
            algorithm="HS256",
            key="this is definitely not the real secret",
        )
        response = self.client.get(
            "/data/verified_emails/", HTTP_AUTHORIZATION=f"Bearer: {token}"
        )
        self.assertEqual(response.status_code, 401)

    @freeze_time("2019-02-22 12:25:00 EST")
    def test_expired_token_denied(self):
        """Expired tokens must not work."""
        token = jwt.encode(
            {"exp": int(time.time()) - 1, "email": "tim@mit.edu"},
            algorithm="HS256",
            key="this is definitely not the real secret",
        )
        response = self.client.get(
            "/data/verified_emails/", HTTP_AUTHORIZATION=f"Bearer: {token}"
        )
        self.assertEqual(response.status_code, 401)

    def test_real_secret_works(self):
        """First, we show that requests using a signed, non-expired token work."""
        year_2525 = 17514144000
        real_token = jwt.encode(
            {"exp": year_2525, "email": "tim@mit.edu"},
            algorithm="HS256",
            key=settings.MEMBERSHIP_SECRET_KEY,
        )
        response = self.client.get(
            "/data/verified_emails/", HTTP_AUTHORIZATION=f"Bearer: {real_token}"
        )
        self.assertEqual(response.status_code, 200)

    def test_real_secret_works_with_different_algorithm(self):
        """We also support HMAC with SHA-512."""
        year_2525 = 17514144000
        real_token = jwt.encode(
            {"exp": year_2525, "email": "tim@mit.edu"},
            algorithm="HS512",
            key=settings.MEMBERSHIP_SECRET_KEY,
        )
        response = self.client.get(
            "/data/verified_emails/", HTTP_AUTHORIZATION=f"Bearer: {real_token}"
        )
        self.assertEqual(response.status_code, 200)

    def test_disallowed_algorithm(self):
        """A token signed with the correct secret but the wrong algorithm is denied."""
        year_2525 = 17514144000
        real_token = jwt.encode(
            {"exp": year_2525, "email": "tim@mit.edu"},
            algorithm="HS384",
            key=settings.MEMBERSHIP_SECRET_KEY,
        )
        response = self.client.get(
            "/data/verified_emails/", HTTP_AUTHORIZATION=f"Bearer: {real_token}"
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"message": "invalid algorithm"})

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
            {"exp": year_2525, "email": "tim@mit.edu"}, algorithm="none", key=None
        )
        response = self.client.get(
            "/data/verified_emails/", HTTP_AUTHORIZATION=f"Bearer: {malicious_token}"
        )
        # Because the attacker gave a token without signing the secret, they get a 401
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"message": "invalid algorithm"})


class OtherVerifiedEmailsTest(TestCase):
    """We report what we know about a MITOCer to authenticated APIS."""

    def _query_for(self, email):
        real_token = jwt.encode(
            {"exp": time.time() + 60, "email": email},
            algorithm="HS512",
            key=settings.MEMBERSHIP_SECRET_KEY,
        )
        return self.client.get(
            "/data/verified_emails/", HTTP_AUTHORIZATION=f"Bearer: {real_token}"
        )

    def test_unknown_user(self):
        """We just report back the same email if we don't find a match."""
        response = self._query_for("barry.o@whitehouse.gov")
        self.assertEqual(
            response.json(),
            {
                "name": None,
                "primary": "barry.o@whitehouse.gov",
                "emails": ["barry.o@whitehouse.gov"],
            },
        )

    def test_normal_participant(self):
        """We handle the case of a participant with some verified & unverified emails."""
        tim = factories.ParticipantFactory.create(
            name="Tim Beaver", email="tim@example.com"
        )

        factories.EmailAddressFactory.create(
            user_id=tim.user_id,
            verified=False,
            primary=False,
            # Tim clearly doesn't own this email
            email="tim@whitehouse.gov",
        )
        factories.EmailAddressFactory.create(
            user_id=tim.user_id, verified=True, primary=False, email="tim@mit.edu"
        )

        response = self._query_for("tim@mit.edu")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "name": "Tim Beaver",
                "primary": "tim@example.com",
                "emails": ["tim@example.com", "tim@mit.edu"],
            },
        )
        # We get the same result when querying under a different known email!
        self.assertEqual(response.json(), self._query_for("tim@example.com").json())

    def test_user_without_participant(self):
        """We handle the case of a user who never completed a participant record."""
        factories.UserFactory.create(email="tim@mit.edu")
        response = self._query_for("tim@mit.edu")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "name": None,
                "primary": "tim@mit.edu",
                "emails": ["tim@mit.edu"],
            },
        )


class JsonProgramLeadersViewTest(TestCase):
    def setUp(self):
        super().setUp()
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get("/programs/climbing/leaders.json")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, "/accounts/login/?next=/programs/climbing/leaders.json"
        )

    def test_bad_program(self):
        response = self.client.get("/programs/snowmobiling/leaders.json")
        self.assertEqual(response.status_code, 404)

    def test_no_leaders(self):
        response = self.client.get("/programs/climbing/leaders.json")
        self.assertEqual(response.json(), {"leaders": []})

        factories.LeaderRatingFactory.create(activity=enums.Activity.HIKING.value)
        response = self.client.get("/programs/climbing/leaders.json")
        self.assertEqual(response.json(), {"leaders": []})

    def test_open_program(self):
        """Any active leader is allowed for an open program."""
        factories.LeaderRatingFactory.create(
            rating="Inactive", activity=enums.Activity.BIKING.value, active=False
        )
        h = factories.LeaderRatingFactory.create(
            participant__name="Hiker",
            rating="Leader",
            activity=enums.Activity.HIKING.value,
        )
        c = factories.LeaderRatingFactory.create(
            participant__name="Climber",
            rating="Sport",
            activity=enums.Activity.CLIMBING.value,
        )
        # Climbing leader is also a leader on a different activity!
        # (they will not be counted twice)
        factories.LeaderRatingFactory.create(
            participant=c.participant,
            rating="Downhill",
            activity=enums.Activity.BIKING.value,
        )

        response = self.client.get("/programs/circus/leaders.json")
        self.assertEqual(
            response.json(),
            {
                "leaders": [
                    {"id": c.participant_id, "name": "Climber", "rating": None},
                    {"id": h.participant_id, "name": "Hiker", "rating": None},
                ]
            },
        )

    def test_alphabetical(self):
        """Leaders are sorted by name."""
        c = factories.LeaderRatingFactory.create(participant__name="Carl", rating="A")
        b = factories.LeaderRatingFactory.create(participant__name="Bob", rating="B")
        d = factories.LeaderRatingFactory.create(participant__name="Dee", rating="I")
        a = factories.LeaderRatingFactory.create(participant__name="Alice", rating="C")
        activity = a.activity_enum.value

        response = self.client.get(f"/programs/{activity}/leaders.json")
        self.assertEqual(
            response.json(),
            {
                "leaders": [
                    {"id": a.participant_id, "name": "Alice", "rating": "C"},
                    {"id": b.participant_id, "name": "Bob", "rating": "B"},
                    {"id": c.participant_id, "name": "Carl", "rating": "A"},
                    {"id": d.participant_id, "name": "Dee", "rating": "I"},
                ]
            },
        )

    def test_inactive_ratings_excluded(self):
        factories.LeaderRatingFactory.create(
            rating="Inactive", activity=enums.Activity.BIKING.value, active=False
        )

        # A participant with an old (inactive) rating only includes the active one
        jane = factories.ParticipantFactory.create(name="Jane Ng")
        factories.LeaderRatingFactory.create(
            rating="Co-leader",
            participant=jane,
            activity=enums.Activity.BIKING.value,
            active=False,
        )
        factories.LeaderRatingFactory.create(
            rating="Leader",
            participant=jane,
            activity=enums.Activity.BIKING.value,
            active=True,
        )
        response = self.client.get("/programs/biking/leaders.json")
        self.assertEqual(
            response.json(),
            {"leaders": [{"id": jane.pk, "name": "Jane Ng", "rating": "Leader"}]},
        )

    def test_latest_rating_taken(self):
        """If, somehow multiple active ratings exist, we don't duplicate!"""
        par = factories.ParticipantFactory.create(name="Steve O")

        with freeze_time("2019-02-22 12:25:00 EST"):
            factories.LeaderRatingFactory.create(
                rating="A",
                participant=par,
                activity=enums.Activity.WINTER_SCHOOL.value,
                active=True,
            )
        with freeze_time("2019-03-30 12:25:00 EST"):
            factories.LeaderRatingFactory.create(
                rating="B",
                participant=par,
                activity=enums.Activity.WINTER_SCHOOL.value,
                active=True,
            )
        with freeze_time("2019-04-04 12:25:00 EST"):
            factories.LeaderRatingFactory.create(
                rating="C",
                participant=par,
                activity=enums.Activity.WINTER_SCHOOL.value,
                active=True,
            )

        response = self.client.get("/programs/winter_school/leaders.json")
        self.assertEqual(
            response.json(),
            {"leaders": [{"id": par.pk, "name": "Steve O", "rating": "C"}]},
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
        response = self.client.get("/participants.json")
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get("/participants.json")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/?next=/participants.json")

    @staticmethod
    def _expect(par):
        return {
            "id": par.pk,
            "name": par.name,
            "email": par.email,
            "avatar": mock.ANY,  # (we test elsewhere)
        }

    def test_search(self):
        michaela = factories.ParticipantFactory.create(name="Michaela the MITOCer")
        michele = factories.ParticipantFactory.create(name="Michele da Italia")
        miguel = factories.ParticipantFactory.create(name="Miguel Michele")
        factories.ParticipantFactory.create(name="Aaron Blake")

        searcher = {
            "id": self.participant.pk,
            "name": "Mr. Bolton",
            "email": "michael@example.com",  # Match was on email, not name
            "avatar": "https://www.gravatar.com/avatar/03ea78c0884c9ac0f73e6af7b9649e90?d=mm&s=200&r=pg",
        }

        others = [self._expect(michaela), self._expect(michele), self._expect(miguel)]

        # Search for something nobody will match on.
        response = self.client.get("/participants.json?search=Michelada")
        self.assertEqual(response.json(), {"participants": []})

        # Search everybody matching 'mich' (matches all but Aaron)
        response = self.client.get("/participants.json?search=Mich")
        matches = response.json()["participants"]
        # TODO: Once using FTS or something, assert order.
        # For now, we just return in any given order.
        self.assertCountEqual(matches, [searcher, *others])

        # Exclude self when searching
        response = self.client.get("/participants.json?search=Mich&exclude_self=1")
        no_self_matches = response.json()["participants"]
        self.assertCountEqual(no_self_matches, others)

    def test_exact_id(self):
        """Participants can be queried by an exact ID."""
        one = factories.ParticipantFactory.create()
        two = factories.ParticipantFactory.create()
        factories.ParticipantFactory.create()

        response = self.client.get(f"/participants.json?id={one.pk}&id={two.pk}")
        self.assertEqual(
            response.json(), {"participants": [self._expect(one), self._expect(two)]}
        )


class JsonLeaderParticipantSignupTest(TestCase):
    def setUp(self):
        super().setUp()
        self.trip = factories.TripFactory.create(algorithm="lottery")
        self.url = f"/trips/{self.trip.pk}/signup/"
        self.leader = factories.ParticipantFactory.create()
        self.trip.leaders.add(self.leader)
        self.client.force_login(self.leader.user)

    def test_just_user(self):
        """A user without a participant record gets a 403 trying to sign up a user."""
        user = factories.UserFactory.create()
        self.client.force_login(user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated(self):
        """One must obviously be logged in to sign up others."""
        self.client.logout()
        response = self.client.post(self.url)
        # This is a JSON route - it probably shouldn't return with a redirect. Ah, well.
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/accounts/login/?next={self.url}")

    def test_not_a_leader(self):
        """Participants must be a leader for the trip in question."""
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)

    def test_leader_but_not_on_the_trip(self):
        """Participants must be a leader for the trip in question."""
        other_trip = factories.TripFactory.create()
        response = self.client.post(f"/trips/{other_trip.pk}/signup/")
        self.assertEqual(response.status_code, 403)

    def test_unknown_target_participant(self):
        """If the caller is a leader, we'll tell them if the participant isn't found."""
        response = self.client.post(
            self.url,
            {"participant_id": -37},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"message": "No participant found"})

    def test_signup_exists_but_not_on_lottery_trip(self):
        """We won't edit notes and the trip remains in lottery mode."""
        signup = factories.SignUpFactory.create(
            on_trip=False, trip=self.trip, notes="original, participant-supplied notes"
        )
        response = self.client.post(
            self.url,
            {"participant_id": signup.participant.pk, "notes": "leader notes"},
            content_type="application/json",
        )

        # Participant was already signed up for the lottery
        self.assertEqual(self.trip.algorithm, "lottery")
        self.assertEqual(response.status_code, 200)
        signup.refresh_from_db()
        self.assertFalse(signup.on_trip)
        self.assertEqual(signup.notes, "original, participant-supplied notes")

    def test_signup_exists_but_not_on_fcfs_trip(self):
        """We won't edit notes, but we can add the participant to the trip."""
        signup = factories.SignUpFactory.create(
            on_trip=False, trip=self.trip, notes="original, participant-supplied notes"
        )

        self.trip.algorithm = "fcfs"
        self.trip.save()

        response = self.client.post(
            self.url,
            {"participant_id": signup.participant.pk, "notes": "leader notes"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        signup.refresh_from_db()
        self.assertTrue(signup.on_trip)
        self.assertEqual(signup.notes, "original, participant-supplied notes")

    def test_new_signup_to_fcfs_trip(self):
        """Test the simplest case: adding a participant to a FCFS trip with spaces."""
        self.trip.algorithm = "fcfs"
        self.trip.save()

        par = factories.ParticipantFactory.create()

        response = self.client.post(
            self.url,
            {"participant_id": par.pk, "notes": "leader notes"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        signup = models.SignUp.objects.get(participant=par, trip=self.trip)
        self.assertTrue(signup.on_trip)
        self.assertEqual(signup.notes, "leader notes")

    def test_add_new_waitlist_entry(self):
        """We can add a participant to the waitlist for a full trip."""
        self.trip.algorithm = "fcfs"
        self.trip.maximum_participants = 1
        self.trip.save()

        # Trip is full now
        factories.SignUpFactory.create(trip=self.trip)

        par = factories.ParticipantFactory.create()

        response = self.client.post(
            self.url,
            {"participant_id": par.pk},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        signup = models.SignUp.objects.get(participant=par, trip=self.trip)
        self.assertFalse(signup.on_trip)
        self.assertTrue(signup.waitlistsignup)
        self.assertEqual(signup.notes, "")

    def test_already_on_trip(self):
        """Leaders can't add a participant already on the trip!"""
        signup = factories.SignUpFactory.create(
            trip=self.trip, on_trip=True, participant__name="Abdul McTest"
        )

        response = self.client.post(
            self.url,
            {"participant_id": signup.participant_id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"message": "Abdul McTest is already on the trip"}
        )

    def test_already_on_waitlist(self):
        """Leaders can't add a participant already on the waitlist!"""
        self.trip.algorithm = "fcfs"
        self.trip.maximum_participants = 1
        self.trip.save()

        # Trip is full now
        factories.SignUpFactory.create(trip=self.trip)

        signup = factories.SignUpFactory.create(
            trip=self.trip, participant__name="Jane McJaney"
        )
        add_to_waitlist(signup)

        response = self.client.post(
            self.url,
            {"participant_id": signup.participant_id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.json(), {"message": "Jane McJaney is already on the waitlist"}
        )


class ApproveTripViewTest(TestCase):
    def setUp(self):
        super().setUp()
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def _approve(self, trip, approved=True):
        return self.client.post(
            f"/trips/{trip.pk}/approve/",
            {"approved": approved},
            content_type="application/json",
        )

    def test_unknown_activity(self):
        trip = factories.TripFactory.create(program=enums.Program.CIRCUS.value)
        response = self._approve(trip)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"message": "No chair for Circus"})

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


class RawMembershipStatsviewTest(TestCase):
    def setUp(self):
        super().setUp()
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)
        factories.LeaderRatingFactory.create(participant=self.participant)

    def test_must_be_leader(self):
        models.LeaderRating.objects.filter(participant=self.participant).delete()
        response = self.client.get("/stats/membership.json")
        self.assertEqual(response.status_code, 403)

    def test_invalid_cache_strategy(self):
        response = self.client.get("/stats/membership.json?cache_strategy=delete")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {
                "message": "Cache strategy must be one of default, fetch_if_stale, bypass"
            },
        )

    def test_first_load_inits_cache(self):
        self.assertFalse(models.MembershipStats.objects.exists())
        with freeze_time("2019-02-22 12:25:00 EST"):
            with mock.patch.object(tasks.update_member_stats, "delay"):
                response = self.client.get("/stats/membership.json")
        self.assertTrue(models.MembershipStats.objects.exists())

        self.assertEqual(
            response.json(),
            # Yeah, technically this is a bit misleading since we've retrieved nothing.
            # Oh well, will only mislead on its first load.
            {"retrieved_at": "2019-02-22T12:25:00-05:00", "members": []},
        )

    @responses.activate
    def test_fetches_async_by_default(self):
        with freeze_time("2019-02-22 12:25:00 EST"):
            cached = models.MembershipStats.load()
            cached.response = [
                {
                    "id": 37,
                    "affiliation": "MIT undergrad",
                    "alternate_emails": ["tim@mit.edu"],
                    "email": "tim@example.com",
                    "num_rentals": 3,
                }
            ]
            cached.save()

        factories.EmailAddressFactory.create(
            user=self.participant.user,
            email="tim@example.com",
            verified=True,
            primary=False,
        )
        factories.SignUpFactory.create(participant=self.participant, on_trip=True)

        with mock.patch.object(tasks.update_member_stats, "delay") as update:
            response = self.client.get("/stats/membership.json")  # No cache_strategy
        update.assert_called_once_with(3600)

        self.assertEqual(
            response.json(),
            {
                # We used the cached information from the geardb
                "retrieved_at": "2019-02-22T12:25:00-05:00",
                "members": [
                    {
                        "email": self.participant.email,
                        "affiliation": "MIT undergrad",
                        "num_rentals": 3,
                        # Notably, augmented by fresh trips info!
                        "is_leader": True,
                        "num_trips_attended": 1,
                        "num_trips_led": 0,
                        "num_discounts": 0,
                    },
                ],
            },
        )

    @responses.activate
    def test_no_members(self):
        responses.get(url="https://mitoc-gear.mit.edu/api-auth/v1/stats", json=[])
        with freeze_time("2019-02-22 12:25:00 EST"):
            response = self.client.get("/stats/membership.json?cache_strategy=bypass")
        self.assertEqual(
            response.json(),
            {"retrieved_at": "2019-02-22T12:25:00-05:00", "members": []},
        )

    @responses.activate
    def test_no_matching_participant(self):
        responses.get(
            url="https://mitoc-gear.mit.edu/api-auth/v1/stats",
            json=[
                {
                    "id": 37,
                    "affiliation": "MIT undergrad",
                    "alternate_emails": ["tim@mit.edu"],
                    "email": "tim@example.com",
                    "num_rentals": 3,
                }
            ],
        )
        self._expect_members(
            {
                "email": "tim@example.com",
                "affiliation": "MIT undergrad",
                "num_rentals": 3,
            }
        )

    def _expect_members(self, *expected_members: MemberInfo) -> None:
        response = self.client.get("/stats/membership.json?cache_strategy=bypass")
        resp_json = response.json()
        self.assertCountEqual(resp_json, {"members", "retrieved_at"})
        self.assertCountEqual(resp_json["members"], expected_members)

    @responses.activate
    def test_matches_on_verified_emails_only(self) -> None:
        responses.get(
            url="https://mitoc-gear.mit.edu/api-auth/v1/stats",
            json=[
                {
                    "id": 42,
                    "affiliation": "Non-MIT undergrad",
                    "alternate_emails": ["bob@bu.edu"],
                    "email": "bob@example.com",
                    "num_rentals": 0,
                },
                {
                    "id": 404,
                    "affiliation": "MIT affiliate",
                    "alternate_emails": [],
                    "email": "404@example.com",
                    "num_rentals": 0,
                },
            ],
        )

        # Matches on a verified email!
        bob = factories.ParticipantFactory.create(email="bob+preferred@example.com")
        factories.EmailAddressFactory.create(
            user=bob.user, email="bob@bu.edu", verified=True, primary=False
        )

        # Email isn't verified, so no match
        wat = factories.ParticipantFactory.create(email="404@gmail.com")
        factories.EmailAddressFactory.create(
            user=wat.user, email="404@example.com", verified=False
        )

        self._expect_members(
            {
                # We report their trips email as preferred!
                "email": "bob+preferred@example.com",
                "affiliation": "Non-MIT undergrad",
                # Found a matching account!
                "is_leader": False,
                "num_discounts": 0,
                "num_rentals": 0,
                "num_trips_attended": 0,
                "num_trips_led": 0,
            },
            # We did not find a matching trips account
            {
                "affiliation": "MIT affiliate",
                "email": "404@example.com",
                "num_rentals": 0,
            },
        )

    @responses.activate
    def test_trips_data_included(self):
        responses.get(
            url="https://mitoc-gear.mit.edu/api-auth/v1/stats",
            json=[
                {
                    "id": 42,
                    "affiliation": "Non-MIT undergrad",
                    "alternate_emails": ["bob@bu.edu"],
                    "email": "bob@example.com",
                    "num_rentals": 0,
                },
                {
                    "id": 37,
                    "affiliation": "MIT undergrad",
                    "alternate_emails": ["tim@MIT.EDU"],  # Case-insensitive!
                    "email": "tim@EXAMPLE.COM",
                    "num_rentals": 3,
                },
                {
                    "id": 404,
                    "affiliation": "MIT affiliate",
                    "alternate_emails": [],
                    "email": "404@example.com",
                    "num_rentals": 0,
                },
            ],
        )

        factories.EmailAddressFactory.create(
            user=self.participant.user,
            email="tim@example.com",
            verified=True,
            primary=False,
        )
        bob = factories.ParticipantFactory.create(email="bob+bu@example.com")
        factories.EmailAddressFactory.create(
            user=bob.user, email="bob@bu.edu", verified=True, primary=False
        )

        # Bob's been on 1 trip
        factories.SignUpFactory.create(participant=bob, on_trip=True)
        factories.SignUpFactory.create(participant=bob, on_trip=False)

        # Has led 2 trips, but not presently a leader
        factories.LeaderRatingFactory.create(participant=bob, active=False)
        factories.TripFactory.create().leaders.add(bob)
        factories.TripFactory.create().leaders.add(bob)

        # Tim has been on 2 trips, led 1
        factories.SignUpFactory.create(participant=self.participant, on_trip=True)
        factories.SignUpFactory.create(participant=self.participant, on_trip=True)
        factories.SignUpFactory.create(participant=self.participant, on_trip=False)

        # Has led 1 trip, but not presently a leader
        factories.LeaderRatingFactory.create(participant=self.participant, active=False)
        factories.TripFactory.create().leaders.add(self.participant)

        # Enjoys one discount, administers another!
        discount = factories.DiscountFactory.create()
        self.participant.discounts.add(discount)
        factories.DiscountFactory.create().administrators.add(self.participant)

        self._expect_members(
            {
                "email": "bob+bu@example.com",  # Preferred email!
                "affiliation": "Non-MIT undergrad",
                "num_rentals": 0,
                "is_leader": False,  # Not presently a leader!
                "num_trips_attended": 1,
                "num_trips_led": 2,
                "num_discounts": 0,
            },
            {
                "email": self.participant.email,
                "affiliation": "MIT undergrad",
                "num_rentals": 3,
                "is_leader": True,
                "num_trips_attended": 2,
                "num_trips_led": 1,
                "num_discounts": 1,
            },
            # We did not find a matching trips account
            {
                "affiliation": "MIT affiliate",
                "email": "404@example.com",
                "num_rentals": 0,
            },
        )

        # Ignoring the overhead of API queries, this is an efficient endpoint!
        # 1. Read cache object (or create)
        # 2. Save cache
        with self.assertNumQueries(2):
            stats = member_stats.fetch_geardb_stats_for_all_members(
                member_stats.CacheStrategy.BYPASS
            )

        # 1. Count trips per participant (separate to avoid double-counting)
        # 2. Count discounts, trips led, per participant
        # 3. Get all emails (lowercased, for mapping back to participant records)
        with self.assertNumQueries(3):
            stats.with_trips_information()
