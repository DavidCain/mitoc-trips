from bs4 import BeautifulSoup
from django.test import TestCase
from freezegun import freeze_time

from ws import models
from ws.tests import factories, strip_whitespace


class MembershipStatsViewTest(TestCase):
    def setUp(self):
        super().setUp()
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)
        factories.LeaderRatingFactory.create(participant=self.participant)

    def test_must_be_leader(self):
        models.LeaderRating.objects.filter(participant=self.participant).delete()
        response = self.client.get("/stats/membership.json")
        self.assertEqual(response.status_code, 403)

    def test_membership_stats(self):
        with freeze_time("2020-01-12 09:00:00 EST"):
            models.MembershipStats.load()

        response = self.client.get("/stats/membership/")
        soup = BeautifulSoup(response.content, "html.parser")

        # The JSON is provided for anybody who wants it
        self.assertTrue(soup.find("a", href="/stats/membership.json"))

        # We report the cache date+time
        self.assertEqual(
            strip_whitespace(soup.find("small").text),
            "Membership stats retrieved Jan. 12, 2020, 9 a.m.",
        )

        # We provide an easy option to bypass the cache
        self.assertTrue(
            soup.find(
                "a",
                href="/stats/membership/?cache_strategy=bypass",
                string="Query servers for the latest?",
            )
        )

    def test_unknown_cache_strategy_redirects(self):
        response = self.client.get("/stats/membership/?cache_strategy=wat")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/stats/membership/")

    def test_bypass_cache(self):
        response = self.client.get("/stats/membership/?cache_strategy=bypass")

        # We'll instruct the JS to honor the caching strategy!
        self.assertIn(
            b'.load("/stats/membership.json?cache_strategy=bypass")',
            response.content,
        )
        # We don't report the last-cached time, since we'll refresh
        self.assertNotIn(b"Membership stats retrieved", response.content)
