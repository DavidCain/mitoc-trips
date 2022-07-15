from django.test import TestCase
from freezegun import freeze_time

from ws import enums, models
from ws.tests import factories

ACTIVITIES_WITH_APPLICATIONS = [
    enums.Activity.CLIMBING,  # Special case: it's a Google form
    enums.Activity.HIKING,
    enums.Activity.WINTER_SCHOOL,
]

ACTIVITIES_WITHOUT_APPLICATIONS = [
    enums.Activity.BIKING,
    enums.Activity.BOATING,
    enums.Activity.CABIN,
]


class AcceptingApplicationsTest(TestCase):
    def test_enumerations_comprehensive(self):
        """The above categorizations are comprehensive."""
        self.assertCountEqual(
            enums.Activity,
            [*ACTIVITIES_WITH_APPLICATIONS, *ACTIVITIES_WITHOUT_APPLICATIONS],
        )

    def test_no_form_not_accepting(self):
        """Activities without a defined form are not accepting applications."""
        for activity_enum in ACTIVITIES_WITHOUT_APPLICATIONS:
            activity = activity_enum.value
            self.assertFalse(models.LeaderApplication.can_apply_for_activity(activity))
            self.assertFalse(models.LeaderApplication.accepting_applications(activity))

    def test_always_accepting(self):
        """Some activities are always accepting applications."""
        self.assertTrue(
            models.LeaderApplication.accepting_applications(enums.Activity.HIKING.value)
        )

    def test_ws_accepting_by_default(self):
        # Settings don't exist to begin with (they'll be created on first access)
        self.assertFalse(models.WinterSchoolSettings.objects.exists())
        self.assertTrue(
            models.LeaderApplication.accepting_applications(
                enums.Activity.WINTER_SCHOOL.value
            )
        )

        ws_settings = models.WinterSchoolSettings.load()
        self.assertTrue(ws_settings.accept_applications)

    def test_ws_not_accepting(self):
        ws_settings = models.WinterSchoolSettings.load()
        ws_settings.accept_applications = False
        ws_settings.save()
        self.assertFalse(ws_settings.accept_applications)


class CanReapplyTest(TestCase):
    @freeze_time("2019-11-22 12:25:00 EST")
    def test_ws_only_apply_once_in_a_year(self):
        # It's currently 2019, 2020 is the next season
        last_app = factories.WinterSchoolLeaderApplicationFactory.create(year=2020)
        self.assertFalse(models.WinterSchoolLeaderApplication.can_reapply(last_app))

    @freeze_time("2019-11-22 12:25:00 EST")
    def test_ws_apply_annually(self):
        last_app = factories.WinterSchoolLeaderApplicationFactory.create(year=2019)
        self.assertTrue(models.WinterSchoolLeaderApplication.can_reapply(last_app))

    def test_upgrade_vs_new(self):
        participant = factories.ParticipantFactory.create()

        with freeze_time("2019-04-02 09:00:00 EST"):
            last_app = factories.HikingLeaderApplicationFactory.create(
                participant=participant
            )

        def can_reapply():
            return models.HikingLeaderApplication.can_reapply(last_app)

        # 6 months must pass to re-apply!
        with freeze_time("2019-09-28 09:00:00 EST"):
            self.assertFalse(can_reapply())
        with freeze_time("2019-10-03 09:00:00 EST"):
            self.assertTrue(can_reapply())

        # An upgrade is allowed after 2 weeks, though!
        factories.LeaderRatingFactory.create(
            participant=participant, activity=models.LeaderRating.HIKING
        )
        with freeze_time("2019-04-12 09:00:00 EST"):
            self.assertFalse(can_reapply())
        with freeze_time("2019-04-16 12:00:00 EST"):
            self.assertTrue(can_reapply())
