from freezegun import freeze_time

from ws import models
from ws.tests import TestCase, factories


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
            last_app = factories.ClimbingLeaderApplicationFactory.create(
                participant=participant
            )

        def can_reapply():
            return models.ClimbingLeaderApplication.can_reapply(last_app)

        # 6 months must pass to re-apply!
        with freeze_time("2019-09-28 09:00:00 EST"):
            self.assertFalse(can_reapply())
        with freeze_time("2019-10-03 09:00:00 EST"):
            self.assertTrue(can_reapply())

        # An upgrade is allowed after 2 weeks, though!
        factories.LeaderRatingFactory.create(
            participant=participant, activity=models.LeaderRating.CLIMBING
        )
        with freeze_time("2019-04-12 09:00:00 EST"):
            self.assertFalse(can_reapply())
        with freeze_time("2019-04-16 12:00:00 EST"):
            self.assertTrue(can_reapply())
