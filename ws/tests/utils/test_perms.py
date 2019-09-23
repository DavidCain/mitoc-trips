from django.contrib.auth.models import AnonymousUser, User

from ws import models
from ws.tests import TestCase
from ws.tests.factories import ParticipantFactory, TripFactory, UserFactory
from ws.utils import perms as perm_utils


class PermUtilTests(TestCase):
    def test_anonymous_leaders(self):
        """ Anonymous users are never leaders, chairs, etc.. """
        anon = AnonymousUser()
        self.assertFalse(perm_utils.is_leader(anon), False)
        self.assertFalse(perm_utils.is_chair(anon, 'climbing'), False)
        self.assertFalse(perm_utils.in_any_group(anon, ['group_name']), False)

    def test_leader_on_trip_creator(self):
        trip = TripFactory()
        self.assertTrue(
            perm_utils.leader_on_trip(trip.creator, trip, creator_allowed=True)
        )
        self.assertFalse(
            perm_utils.leader_on_trip(trip.creator, trip, creator_allowed=False)
        )

    def test_leader_on_trip(self):
        trip = TripFactory()
        self.assertFalse(perm_utils.leader_on_trip(trip.creator, trip))
        trip.leaders.add(trip.creator)
        self.assertTrue(perm_utils.leader_on_trip(trip.creator, trip))

    def test_open_activities_no_chair(self):
        """ Open activities never have a chair. """
        user = AnonymousUser()  # Won't ever be checked anyway

        # models.BaseRating.OPEN_ACTIVITIES
        for activity in ['circus', 'official_event', 'course']:
            self.assertFalse(perm_utils.is_chair(user, activity), False)
            with self.assertRaises(ValueError):
                perm_utils.chair_group(activity)

    def test_activity_name(self):
        """ Activity names are translated to human-readable labels. """
        activity_translations = {
            'winter_school': 'Winter School',
            'climbing': 'Climbing',
            'hiking': 'Hiking',
        }
        for activity, label in activity_translations.items():
            self.assertEqual(perm_utils.activity_name(activity), label)

    def test_cannot_get_chair_for_open_activity(self):
        """ Open activities don't have a chair! """
        with self.assertRaises(ValueError):
            perm_utils.chair_group(models.BaseRating.OFFICIAL_EVENT)

    def test_cannot_make_chair_for_open_activity(self):
        """ You can't make somebody the chair of an open activity. """
        valid_participant = ParticipantFactory.create()
        open_activity = models.BaseRating.OFFICIAL_EVENT
        with self.assertRaises(ValueError):
            perm_utils.make_chair(valid_participant.user, open_activity)

    def test_make_chair(self):
        """ Users can be promoted to being activity chairs. """
        # To begin with, our user is not a chair (nobody is, for that matter)
        climbing = models.BaseRating.CLIMBING
        user = UserFactory.create()
        self.assertFalse(perm_utils.is_chair(user, climbing))
        self.assertEqual(perm_utils.num_chairs(climbing), 0)

        # We promote them to be a climbing chair
        perm_utils.make_chair(user, climbing)
        self.assertTrue(perm_utils.is_chair(user, climbing))
        self.assertEqual(perm_utils.num_chairs(climbing), 1)

        # chair_or_admin works now too, and the user is definitely not a superuser
        self.assertTrue(perm_utils.chair_or_admin(user, climbing))
        self.assertFalse(user.is_superuser)

        # Sanity check: The user wasn't accidentally made the chair of other activities
        self.assertFalse(perm_utils.is_chair(user, models.BaseRating.BOATING))


class SuperUserTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin = User.objects.create_superuser(
            'admin', 'admin@example.com', 'password'
        )
        super().setUpClass()

    def test_activity_chair(self):
        """ The admin can be considered an activity chair in some contexts. """

        self.assertTrue(perm_utils.chair_or_admin(self.admin, models.BaseRating.HIKING))
        self.assertTrue(perm_utils.is_chair(self.admin, models.BaseRating.HIKING))
        self.assertTrue(
            perm_utils.is_chair(
                self.admin, models.BaseRating.HIKING, allow_superusers=True
            )
        )
        self.assertFalse(
            perm_utils.is_chair(
                self.admin, models.BaseRating.HIKING, allow_superusers=False
            )
        )

    def test_chair_activities(self):
        """ The admin qualifies as a chair when allow_superusers is set. """
        # This admin is not a chair in the normal context
        self.assertFalse(
            perm_utils.chair_activities(self.admin, allow_superusers=False)
        )
        self.assertFalse(perm_utils.chair_activities(self.admin))

        allowed_activities = set(
            perm_utils.chair_activities(self.admin, allow_superusers=True)
        )

        # Considered the chair for closed activities
        self.assertEqual(allowed_activities, set(models.BaseRating.CLOSED_ACTIVITIES))
        # No open activities are included in the set
        self.assertFalse(
            allowed_activities.intersection(models.BaseRating.OPEN_ACTIVITIES)
        )

    def test_admin_not_counted_in_list(self):
        """ The admin isn't considered in the count of chairs. """
        self.assertEqual(perm_utils.num_chairs(models.BaseRating.CLIMBING), 0)
