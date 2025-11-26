import unittest
from datetime import date

from bs4 import BeautifulSoup
from django.http import HttpResponseRedirect
from django.test import TestCase
from freezegun import freeze_time

from ws import enums, models
from ws.tests import factories, strip_whitespace
from ws.views import stats


class SummarizeFiltersTest(unittest.TestCase):
    def test_just_start_date(self) -> None:
        self.assertEqual(
            stats.summarize_filters(
                {
                    "q": "",
                    "start_date": date(2024, 12, 1),
                    "end_date": None,
                    "program": "",
                    "winter_terrain_level": "",
                    "trip_type": "",
                }
            ),
            "All trips led since 2024-12-01",
        )

    def test_date_range(self) -> None:
        self.assertEqual(
            stats.summarize_filters(
                {
                    "q": "",
                    "start_date": date(2024, 12, 1),
                    "end_date": date(2025, 11, 30),
                    "program": "",
                    "winter_terrain_level": "",
                    "trip_type": "",
                }
            ),
            "All trips led between 2024-12-01 and 2025-11-30",
        )

    def test_program(self) -> None:
        self.assertEqual(
            stats.summarize_filters(
                {
                    "q": "",
                    "start_date": date(2024, 12, 1),
                    "end_date": None,
                    "program": "winter_school",
                    "winter_terrain_level": "",
                    "trip_type": "",
                }
            ),
            "Winter School trips led since 2024-12-01",
        )

    def test_program_and_trip_type(self) -> None:
        self.assertEqual(
            stats.summarize_filters(
                {
                    "q": "",
                    "start_date": date(2024, 12, 1),
                    "end_date": None,
                    "program": "climbing",
                    "winter_terrain_level": "",
                    "trip_type": "climbing_trad",
                }
            ),
            "Trad climbing trips led since 2024-12-01, Climbing",
        )

    def test_all_filters(self) -> None:
        self.assertEqual(
            stats.summarize_filters(
                {
                    "q": "Frankenstein",
                    "start_date": date(2024, 12, 1),
                    "end_date": date(2025, 12, 1),
                    "program": "winter_school",
                    "winter_terrain_level": "B",
                    "trip_type": "climbing_ice",
                }
            ),
            "Ice climbing B 'Frankenstein' trips led between 2024-12-01 and 2025-12-01, Winter School",
        )


class LeaderboardTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        # Intentionally create leaders such that PKs are not alphabetical by name.
        self.tim = factories.ParticipantFactory.create(
            name="Tim Beaver", email="tim@mit.edu"
        )
        self.emily = factories.ParticipantFactory.create(
            name="Emily Emory", email="emily@emory.edu"
        )
        self.harry = factories.ParticipantFactory.create(
            name="Harold Harvard", email="harry@harvard.edu"
        )

        self.client.force_login(self.tim.user)
        factories.LeaderRatingFactory.create(participant=self.tim)

    def _set_up_trips(self) -> None:
        # Trips that tests will intentionally exclude
        for will_not_match in [
            factories.TripFactory.create(
                # Out of date range
                trip_date=date(2023, 1, 13),
                program=enums.Program.CLIMBING.value,
                trip_type=enums.TripType.TRAD_CLIMBING.value,
            ),
            factories.TripFactory.create(
                trip_date=date(2023, 12, 25),
                program=enums.Program.CLIMBING.value,
                # Wrong trip type
                trip_type=enums.TripType.GYM_CLIMBING.value,
            ),
        ]:
            will_not_match.leaders.add(self.tim)
            will_not_match.leaders.add(self.emily)
            will_not_match.leaders.add(self.harry)

        # Trips we'll actually consider in the leaderboard!
        jan_2024 = factories.TripFactory.create(
            trip_date=date(2024, 1, 13),
            program=enums.Program.CLIMBING.value,
            trip_type=enums.TripType.TRAD_CLIMBING.value,
        )
        jan_2025 = factories.TripFactory.create(
            trip_date=date(2025, 1, 11), program=enums.Program.WINTER_SCHOOL.value
        )
        dec_2025 = factories.TripFactory.create(
            trip_date=date(2025, 12, 1), program=enums.Program.WINTER_NON_IAP.value
        )

        jan_2024.leaders.add(self.tim)
        jan_2025.leaders.add(self.tim)
        dec_2025.leaders.add(self.tim)

        jan_2024.leaders.add(self.emily)

        jan_2024.leaders.add(self.harry)
        jan_2025.leaders.add(self.harry)

    def test_must_be_logged_in(self) -> None:
        self.client.logout()
        response = self.client.get("/stats/leaderboard/")
        self.assertEqual(response.status_code, 302)
        assert isinstance(response, HttpResponseRedirect)
        self.assertEqual(
            response.url,
            "/accounts/login/?next=/stats/leaderboard/",
        )

    def test_must_be_leader(self) -> None:
        models.LeaderRating.objects.filter(participant=self.tim).delete()
        response = self.client.get("/stats/leaderboard/")
        self.assertEqual(response.status_code, 403)

    def test_default(self) -> None:
        self._set_up_trips()
        with freeze_time("2025-11-15 09:00:00 EST"):
            response = self.client.get("/stats/leaderboard/")
        soup = BeautifulSoup(response.content, "html.parser")

        # We only show the "clear filters" button if there are filters to clear
        self.assertIsNone(soup.find("a", class_="btn-default"))

        header = soup.find("h1")
        assert header is not None
        self.assertEqual(header.text, "All trips led since 2024-11-15")
        tbody = soup.find("tbody")
        assert tbody is not None
        self.assertIn("Tim Beaver", tbody.text)
        self.assertIn("Harold Harvard", tbody.text)
        self.assertNotIn("Emily Emory", tbody.text)

        # 1. Leaders are listed in order of the number of trips they've led.
        # 2. Only programs in the range are rendered.
        # 3. Only leaders who led 1+ trips are shown.
        self.assertEqual(
            response.context["rows"],
            [
                stats.LeaderboardRow(
                    leader=self.tim,
                    total_trips_led=2,
                    trips_led_per_program={
                        enums.Program.WINTER_NON_IAP: 1,
                        enums.Program.WINTER_SCHOOL: 1,
                    },
                ),
                stats.LeaderboardRow(
                    leader=self.harry,
                    total_trips_led=1,
                    trips_led_per_program={
                        enums.Program.WINTER_NON_IAP: 0,
                        enums.Program.WINTER_SCHOOL: 1,
                    },
                ),
            ],
        )
        with freeze_time("2025-11-15 09:00:00 EST"):
            csv_response = self.client.get("/stats/leaderboard.csv")
        self.assertEqual(
            csv_response.getvalue(),
            (
                b"Name,Email,Trips led,Winter (outside IAP),Winter School\r\n"
                b"Tim Beaver,tim@mit.edu,2,1,1\r\n"
                b"Harold Harvard,harry@harvard.edu,1,0,1\r\n"
            ),
        )

    def test_filters(self) -> None:
        self._set_up_trips()
        response = self.client.get(
            "/stats/leaderboard/"
            "?program=climbing"
            # There is a gym climbing trip in Dec of 2023
            "&trip_type=climbing_trad"
            # There will be other non-climbing trips in this range!
            # There will also be climbing trips outside the range.
            "&start_date=2023-12-01"
            "&end_date=2025-02-28"
        )
        soup = BeautifulSoup(response.content, "html.parser")

        clear = soup.find("a", class_="btn-default")
        assert clear is not None
        self.assertEqual(clear.text, "\xa0Clear filters")
        self.assertEqual(clear.attrs["href"], "/stats/leaderboard/")

        header = soup.find("h1")
        assert header is not None
        self.assertEqual(
            header.text,
            "Trad climbing trips led between 2023-12-01 and 2025-02-28, Climbing",
        )

        self.assertEqual(
            response.context["rows"],
            [
                stats.LeaderboardRow(
                    leader=self.emily,
                    total_trips_led=1,
                    trips_led_per_program={enums.Program.CLIMBING: 1},
                ),
                stats.LeaderboardRow(
                    leader=self.harry,
                    total_trips_led=1,
                    trips_led_per_program={enums.Program.CLIMBING: 1},
                ),
                stats.LeaderboardRow(
                    leader=self.tim,
                    total_trips_led=1,
                    trips_led_per_program={enums.Program.CLIMBING: 1},
                ),
            ],
        )


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
