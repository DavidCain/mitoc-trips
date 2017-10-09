from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from ws.utils import perms as perm_utils
from ws.tests.helpers import PermHelpers


class PermUtilTests(PermHelpers, TestCase):
    def test_anonymous_leaders(self):
        """ Anonymous users are never leaders, chairs, etc.. """
        anon = AnonymousUser()
        self.assertFalse(perm_utils.is_leader(anon), False)
        self.assertFalse(perm_utils.is_chair(anon, 'climbing'), False)
        self.assertFalse(perm_utils.in_any_group(anon, ['group_name']), False)

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
