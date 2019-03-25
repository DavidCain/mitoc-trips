from contextlib import contextmanager
from unittest import mock

from django.test import SimpleTestCase

from ws import models
from ws.tests import factories, TestCase
import ws.utils.perms as perm_utils
from ws.utils import ratings


class ApplicationManagerHelper:
    @staticmethod
    def _only_for_climbing(desired_value):
        """ Return the desired value, but only for climbing!

        This makes sure we're not mocking away underlying utils (to get a
        climbing-specific response) only to silently accept the wrong
        activity type.
        """
        def inner_func(activity):
            if activity != models.BaseRating.CLIMBING:
                raise ValueError("This test handles climbing applications!")
            return desired_value
        return inner_func

    @classmethod
    @contextmanager
    def _mock_for_climbing(cls, num_chairs):
        """ Mock away the number of climbing chairs!

        Also mock the query from climbing activity to climbing application, so
        that we need not hit the database.
        """
        get_num_chairs = mock.patch.object(perm_utils, 'num_chairs')
        model_from_activity = mock.patch.object(models.LeaderApplication, 'model_from_activity')
        with get_num_chairs as mock_num_chairs, model_from_activity as mock_app_model:
            mock_app_model.side_effect = cls._only_for_climbing(models.ClimbingLeaderApplication)
            mock_num_chairs.side_effect = cls._only_for_climbing(num_chairs)
            yield


class OneChairTests(TestCase):
    def test_everything_needs_rating_with_one_chair(self):
        """ When there's only one chair, every application needs ratings! """
        chair = factories.ParticipantFactory.create()
        perm_utils.make_chair(chair.user, models.BaseRating.CLIMBING)
        # Filtering is done in Python, no need to save to db
        app1 = factories.ClimbingLeaderApplicationFactory.create()
        app2 = factories.ClimbingLeaderApplicationFactory.create()

        manager = ratings.ApplicationManager(
            chair=chair, activity=models.BaseRating.CLIMBING
        )
        pending_apps = manager.pending_applications()
        self.assertEqual(manager.needs_rating(pending_apps), [app1, app2])


class DatabaselessOneChairTests(SimpleTestCase, ApplicationManagerHelper):
    def test_no_recommendations_needed_with_one_chair(self):
        """ When there's only one chair, no applications need recommendations!

        Recommendations are a mechanism of multiple chairs coming to a consensus
        on a prospective leader's rating. It doesn't make sense for a chair to
        recommend a rating for a particular participant if there aren't other chairs!
        """
        # Filtering is done in Python, no need to save to db
        pending_recs = [
            factories.ClimbingLeaderApplicationFactory.build() for _ in range(3)
        ]
        with self._mock_for_climbing(num_chairs=1):
            manager = ratings.ApplicationManager(activity=models.BaseRating.CLIMBING)
            self.assertEqual(manager.needs_rec(pending_recs), [])


class DatabaseApplicationManagerTests(TestCase):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.alice, self.bob, self.charlie = [
            factories.ParticipantFactory.create() for _ in 'abc'
        ]
        for chair in [self.alice, self.bob, self.charlie]:
            perm_utils.make_chair(chair.user, models.BaseRating.CLIMBING)
        self.application = factories.ClimbingLeaderApplicationFactory.create(
            participant=self.participant)
        super().setUp()

    @staticmethod
    def _manager_for(chair_participant):
        return ratings.ApplicationManager(
            chair=chair_participant, activity=models.BaseRating.CLIMBING
        )

    def _make_recommendation(self, creator):
        rec = models.LeaderRecommendation(
            creator=creator,
            participant=self.participant,
            activity=models.BaseRating.CLIMBING,
            rating='Single pitch, maybe?'  # Comments don't really matter
        )
        rec.save()
        return rec

    def _make_rating(self, creator):
        rating = models.LeaderRating(
            creator=creator,
            participant=self.participant,
            activity=models.BaseRating.CLIMBING,
            rating='Multipitch'
        )
        rating.save()
        return rating

    def test_applications_needing_recommendation(self):
        """ Consider applications without a chair recommendation as requiring one! """
        # We have three chairs!
        self.assertEqual(perm_utils.num_chairs(models.BaseRating.CLIMBING), 3)

        # The application is in a pending state, while awaiting recommendation & rating
        alice_manager = self._manager_for(self.alice)
        pending_apps = alice_manager.pending_applications()
        self.assertEqual(pending_apps, [self.application])
        self.assertEqual(alice_manager.needs_rec(pending_apps), [self.application])

        # Once Alice makes a recommendation, it no longer needs a rec from her
        self._make_recommendation(creator=self.alice)
        # Refresh pending applications, as viewed from Alice's perspective
        pending_apps = alice_manager.pending_applications()
        self.assertEqual(alice_manager.needs_rec(pending_apps), [])

        # The application does, however, need recommendations from the other chairs!
        for other_chair in [self.bob, self.charlie]:
            manager = self._manager_for(other_chair)
            pending_apps = manager.pending_applications()  # From that chair's perspective!
            self.assertEqual(manager.needs_rec(pending_apps), [self.application])

    def test_rating_deactivated(self):
        """ Application is always considered handled if a rating was given afterwards.

        We only consider an application "pending" if the leader in question has
        not been given a leader rating after the date of the actual application.

        It's very common for leader ratings to be deactivated at a later date -
        Winter School ratings are deactivated after each season. Other activity types
        remove leader privileges when leaders move away or otherwise become inactive.
        If we considered applications "pending" just because the person does not have an
        active rating, then lots of old applications would be surfaced.
        """
        # Application starts out needing attention
        charlie_manager = self._manager_for(self.charlie)
        pending_apps = charlie_manager.pending_applications()
        self.assertEqual(pending_apps, [self.application])

        # Another chair gives a rating
        rating = self._make_rating(creator=self.alice)

        # From any chair's perspective, the application does not need attention
        for other_chair in [self.bob, self.charlie]:
            manager = self._manager_for(other_chair)
            pending_apps = manager.pending_applications()  # From that chair's perspective!
            self.assertFalse(pending_apps)
            self.assertFalse(manager.needs_rec(pending_apps))

        rating.active = False
        rating.save()

        # Application is not regarded as "pending"
        self.assertFalse(charlie_manager.pending_applications())
