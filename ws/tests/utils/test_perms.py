from typing import ClassVar

from django.contrib.auth.models import AnonymousUser

from ws import enums, models
from ws.tests import TestCase, factories
from ws.tests.factories import TripFactory, UserFactory
from ws.utils import perms as perm_utils


class PermUtilTests(TestCase):
    def test_chair_group(self):
        self.assertEqual(perm_utils.chair_group(enums.Activity.WINTER_SCHOOL), 'WSC')
        self.assertEqual(
            perm_utils.chair_group(enums.Activity.CLIMBING), 'climbing_chair'
        )
        self.assertEqual(perm_utils.chair_group(enums.Activity.HIKING), 'hiking_chair')

    def test_is_chair_no_activity(self):
        """ When activity is None, `is_chair` is always false! """
        self.assertFalse(perm_utils.is_chair(AnonymousUser(), activity_enum=None))

        # Practical example: a trip with no required activity.
        par = factories.ParticipantFactory.create()
        trip = factories.TripFactory.create(program=enums.Program.SERVICE.value)
        self.assertFalse(perm_utils.is_chair(par, trip.required_activity_enum()))

    def test_anonymous_leaders(self):
        """ Anonymous users are never leaders, chairs, etc.. """
        anon = AnonymousUser()
        self.assertFalse(perm_utils.is_leader(anon), False)
        self.assertFalse(perm_utils.is_chair(anon, enums.Activity.CLIMBING))
        self.assertFalse(perm_utils.in_any_group(anon, ['group_name']))

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

    def test_make_chair(self):
        """ Users can be promoted to being activity chairs. """
        # To begin with, our user is not a chair (nobody is, for that matter)
        user = UserFactory.create()
        self.assertFalse(perm_utils.is_chair(user, enums.Activity.CLIMBING))
        self.assertEqual(perm_utils.num_chairs(enums.Activity.CLIMBING), 0)

        # We promote them to be a climbing chair
        perm_utils.make_chair(user, enums.Activity.CLIMBING)
        self.assertTrue(perm_utils.is_chair(user, enums.Activity.CLIMBING))
        self.assertEqual(perm_utils.num_chairs(enums.Activity.CLIMBING), 1)

        # chair_or_admin works now too, and the user is definitely not a superuser
        self.assertTrue(perm_utils.chair_or_admin(user, enums.Activity.CLIMBING))
        self.assertFalse(user.is_superuser)

        # Sanity check: The user wasn't accidentally made the chair of other activities
        self.assertFalse(perm_utils.is_chair(user, enums.Activity.BOATING))


class SuperUserTestCase(TestCase):
    admin: ClassVar[models.User]

    @classmethod
    def setUpClass(cls):
        cls.admin = factories.UserFactory.create(is_superuser=True)
        super().setUpClass()

    def test_activity_chair(self):
        """ The admin can be considered an activity chair in some contexts. """

        self.assertTrue(perm_utils.chair_or_admin(self.admin, enums.Activity.HIKING))
        self.assertTrue(perm_utils.is_chair(self.admin, enums.Activity.HIKING))
        self.assertTrue(
            perm_utils.is_chair(
                self.admin, enums.Activity.HIKING, allow_superusers=True
            )
        )
        self.assertFalse(
            perm_utils.is_chair(
                self.admin, enums.Activity.HIKING, allow_superusers=False
            )
        )

    def test_chair_activities(self):
        """ The admin qualifies as a chair when allow_superusers is set. """
        # This admin is not a chair in the normal context
        self.assertFalse(
            perm_utils.chair_activities(self.admin, allow_superusers=False)
        )
        self.assertFalse(perm_utils.chair_activities(self.admin))

        admin_allowed_activities = perm_utils.chair_activities(
            self.admin, allow_superusers=True
        )

        # Considered the chair for closed activities
        self.assertCountEqual(admin_allowed_activities, enums.Activity)

    def test_admin_not_counted_in_list(self):
        """ The admin isn't considered in the count of chairs. """
        self.assertEqual(perm_utils.num_chairs(enums.Activity.CLIMBING), 0)
