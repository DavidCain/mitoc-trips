from django.contrib.auth.models import Group
from django.test import TestCase

from ws import models, wimp
from ws.tests import factories


class WimpTests(TestCase):
    def test_no_active_wimps(self) -> None:
        self.assertFalse(Group.objects.get(name="WIMP").user_set.exists())
        self.assertCountEqual(wimp.active_wimps(), [])
        self.assertIsNone(wimp.current_wimp())

    def test_single_wimp(self) -> None:
        wimp_par = factories.ParticipantFactory.create()
        wimp_group = Group.objects.get(name="WIMP")
        self.assertFalse(wimp_group.user_set.exists())

        wimp_group.user_set.add(wimp_par.user)
        self.assertCountEqual(wimp.active_wimps(), [wimp_par])
        self.assertEqual(wimp_par, wimp.current_wimp())

    def test_handle_edge_case_of_user_without_participant(self) -> None:
        no_par_user = factories.UserFactory.create()
        self.assertFalse(
            models.Participant.objects.filter(user_id=no_par_user.pk).exists()
        )

        wimp_par = factories.ParticipantFactory.create()

        wimp_group = Group.objects.get(name="WIMP")
        wimp_group.user_set.add(no_par_user)
        wimp_group.user_set.add(wimp_par.user)
        self.assertCountEqual(wimp.active_wimps(), [wimp_par])
        self.assertEqual(wimp_par, wimp.current_wimp())

    def test_wimps_sorted_by_time_made_wimp(self) -> None:
        wimp_group = Group.objects.get(name="WIMP")

        # Participants are created in different orders
        second_wimp = factories.ParticipantFactory.create()
        first_wimp = factories.ParticipantFactory.create()
        third_wimp = factories.ParticipantFactory.create()

        wimp_group.user_set.add(first_wimp.user)
        wimp_group.user_set.add(second_wimp.user)
        wimp_group.user_set.add(third_wimp.user)

        self.assertEqual(
            list(wimp.active_wimps()), [third_wimp, second_wimp, first_wimp]
        )
        self.assertEqual(third_wimp, wimp.current_wimp())
