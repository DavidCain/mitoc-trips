from contextlib import contextmanager
from unittest import mock

from django.test import SimpleTestCase
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, models
from ws.tests import TestCase, factories
from ws.utils import ratings


class ApplicationManagerHelper:
    @classmethod
    @contextmanager
    def _mock_for_climbing(cls, num_chairs):
        """ Mock away the number of climbing chairs!

        Also mock the query from climbing activity to climbing application, so
        that we need not hit the database.
        """
        get_num_chairs = mock.patch.object(perm_utils, 'num_chairs')
        model_from_activity = mock.patch.object(
            models.LeaderApplication, 'model_from_activity'
        )
        with get_num_chairs as mock_num_chairs, model_from_activity as mock_app_model:
            mock_app_model.return_value = models.ClimbingLeaderApplication
            mock_num_chairs.return_value = num_chairs
            yield

        mock_app_model.assert_called_with(enums.Activity.CLIMBING.value)
        mock_num_chairs.assert_called_with(enums.Activity.CLIMBING)


class OneChairTests(TestCase):
    def test_everything_needs_rating_with_one_chair(self):
        """ When there's only one chair, every application needs ratings! """
        chair = factories.ParticipantFactory.create()
        perm_utils.make_chair(chair.user, enums.Activity.CLIMBING)
        # Filtering is done in Python, no need to save to db
        app1 = factories.ClimbingLeaderApplicationFactory.create()
        app2 = factories.ClimbingLeaderApplicationFactory.create()

        manager = ratings.ApplicationManager(
            chair=chair, activity=enums.Activity.CLIMBING.value
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
            manager = ratings.ApplicationManager(activity=enums.Activity.CLIMBING.value)
            self.assertEqual(manager.needs_rec(pending_recs), [])


class DatabaseApplicationManagerTests(TestCase):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.alice, self.bob, self.charlie = [
            factories.ParticipantFactory.create() for _ in 'abc'
        ]
        for chair in [self.alice, self.bob, self.charlie]:
            perm_utils.make_chair(chair.user, enums.Activity.CLIMBING)
        self.application = factories.ClimbingLeaderApplicationFactory.create(
            participant=self.participant
        )
        super().setUp()

    @staticmethod
    def _manager_for(chair_participant):
        return ratings.ApplicationManager(
            chair=chair_participant, activity=enums.Activity.CLIMBING.value
        )

    def _make_recommendation(self, creator):
        rec = models.LeaderRecommendation(
            creator=creator,
            participant=self.participant,
            activity=enums.Activity.CLIMBING.value,
            rating='Single pitch, maybe?',  # Comments don't really matter
        )
        rec.save()
        return rec

    def _make_rating(self, creator):
        rating = models.LeaderRating(
            creator=creator,
            participant=self.participant,
            activity=enums.Activity.CLIMBING.value,
            rating='Multipitch',
        )
        rating.save()
        return rating

    def test_applications_needing_recommendation(self):
        """ Consider applications without a chair recommendation as requiring one! """
        # We have three chairs!
        self.assertEqual(perm_utils.num_chairs(enums.Activity.CLIMBING), 3)

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
            # Get pending apps from that chair's perspective!
            pending_apps = manager.pending_applications()
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
            # Get pending apps from that chair's perspective!
            pending_apps = manager.pending_applications()
            self.assertFalse(pending_apps)
            self.assertFalse(manager.needs_rec(pending_apps))

        rating.active = False
        rating.save()

        # Application is not regarded as "pending"
        self.assertFalse(charlie_manager.pending_applications())

    def test_archived_application(self):
        """ Archived applications are not shown as pending. """
        self.application.archived = True
        self.application.save()
        manager = self._manager_for(self.bob)
        pending_apps = manager.pending_applications()
        self.assertFalse(pending_apps)


class DeactivateRatingsTest(TestCase):
    @staticmethod
    def test_no_ratings_okay():
        par = factories.ParticipantFactory.create()
        ratings.deactivate_ratings(par, enums.Activity.CLIMBING.value)

    def test_deactivate_ratings(self):
        par = factories.ParticipantFactory.create()

        # Old, inactive ratings aren't touched.
        with freeze_time("2019-02-22 12:22:22 EST"):
            deactivated_activity = factories.LeaderRatingFactory.create(
                activity=enums.Activity.CLIMBING.value,
                participant=par,
                rating='Co-leader',
                active=False,
            )
        with freeze_time("2019-03-30 13:33:33 EST"):
            target_rating = factories.LeaderRatingFactory.create(
                activity=enums.Activity.CLIMBING.value,
                participant=par,
                rating='Full leader',
                active=True,
            )

        # Ratings for other activities aren't touched
        other_activity = factories.LeaderRatingFactory.create(
            activity=enums.Activity.HIKING.value, participant=par
        )

        # Other participants' ratings aren't touched
        same_activity_other_par = factories.LeaderRatingFactory.create(
            activity=enums.Activity.CLIMBING.value
        )

        with freeze_time("2020-04-04 14:00:00 EST"):
            ratings.deactivate_ratings(par, enums.Activity.CLIMBING.value)

        expectations = [
            (deactivated_activity, False),  # unchanged
            (target_rating, False),
            (other_activity, True),
            (same_activity_other_par, True),
        ]
        for rating, is_active in expectations:
            rating.refresh_from_db()
            self.assertEqual(rating.active, is_active)
