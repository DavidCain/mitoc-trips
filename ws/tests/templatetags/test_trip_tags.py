from datetime import date, datetime
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from django.template import Context, Template
from django.test import TestCase
from freezegun import freeze_time

from ws import enums, models
from ws.tests import factories


class TripTagsTest(TestCase):
    @freeze_time("Jan 11 2019 20:30:00 EST")
    def test_simple_trip_list(self):
        trips = [
            factories.TripFactory.create(name="Past Trip", trip_date=date(2017, 8, 2)),
            factories.TripFactory.create(name="Today!", trip_date=date(2019, 1, 11)),
            factories.TripFactory.create(name="Soon Trip", trip_date=date(2019, 1, 16)),
            factories.TripFactory.create(
                name="Later Trip", trip_date=date(2019, 1, 19)
            ),
        ]
        html_template = Template("{% load trip_tags %}{% simple_trip_list trips %}")
        context = Context({"trips": trips})
        soup = BeautifulSoup(html_template.render(context), "html.parser")
        table = soup.find("table")
        heading = table.find("thead").find_all("th")
        self.assertEqual([tr.text for tr in heading], ["Trip", "Date", "Leaders"])

        rows = [tr.find_all("td") for tr in table.find("tbody").find_all("tr")]

        date_per_trip = [
            (trip.find("a").text, rendered_date.text.strip())
            for (trip, rendered_date, _leaders) in rows
        ]
        # We render the dates for each trip unambiguously
        self.assertEqual(
            date_per_trip,
            [
                ("Past Trip", "2017-08-02"),
                ("Today!", "Today"),
                ("Soon Trip", "Wed"),
                ("Later Trip", "Jan 19"),
            ],
        )

    @freeze_time("Jan 10 2019 20:30:00 EST")
    def test_trip_list_approve_mode(self):
        def _ws_trip(trip_date, **kwargs):
            return factories.TripFactory.create(
                program=enums.Program.WINTER_SCHOOL.value,
                trip_date=trip_date,
                **kwargs,
            )

        has_itinerary = _ws_trip(
            date(2019, 1, 11),
            info=factories.TripInfoFactory.create(),
            trip_type=enums.TripType.HIKING.value,
        )
        no_itinerary1 = _ws_trip(
            date(2019, 1, 11), trip_type=enums.TripType.BC_SKIING.value
        )
        no_itinerary2 = _ws_trip(
            date(2019, 1, 11), trip_type=enums.TripType.ICE_CLIMBING.value
        )

        html_template = Template("{% load trip_tags %}{% trip_list_table trips True %}")
        context = Context({"trips": models.Trip.objects.all().order_by("pk")})
        soup = BeautifulSoup(html_template.render(context), "html.parser")

        table = soup.find("table")
        heading = table.find("thead").find_all("th")
        self.assertEqual(
            [tr.text for tr in heading],
            ["Name", "Date", "Terrain level", "Description", "Leaders", "Approve"],
        )

        rows = [tr.find_all("td") for tr in table.find("tbody").find_all("tr")]
        trip_info = [
            {
                "link": row[0].find("a").attrs["href"],
                "icon_classes": row[0].find("i").attrs["class"],
            }
            for row in rows
        ]

        # For each trip, we give a link to the approve page
        self.assertEqual(
            trip_info,
            [
                {
                    "link": f"/winter_school/trips/{has_itinerary.pk}/",
                    "icon_classes": ["fa", "fa-fw", "fa-hiking"],
                },
                {
                    "link": f"/winter_school/trips/{no_itinerary1.pk}/",
                    "icon_classes": ["fa", "fa-fw", "fa-skiing"],
                },
                {
                    "link": f"/winter_school/trips/{no_itinerary2.pk}/",
                    "icon_classes": ["fa", "fa-fw", "fa-icicles"],
                },
            ],
        )

    def test_feedback_for_trip_rated_leader(self):
        leader = factories.ParticipantFactory.create(name="Janet Yellin")
        rating = factories.LeaderRatingFactory.create(
            participant=leader,
            activity=models.BaseRating.CLIMBING,
            rating="Leader",
            active=True,
        )
        leader.leaderrating_set.add(rating)
        feedback = factories.FeedbackFactory.create(
            leader=leader,
            participant__name="Jerome Powell",
            comments="Shows promise",
            trip__name="Free solo 5.13 finger crack climbing",
            trip__program=enums.Program.CLIMBING.value,
        )
        self.assertEqual(str(feedback), 'Jerome Powell: "Shows promise" - Janet Yellin')

        template = Template("{% load trip_tags %}{{ feedback|leader_display }}")
        context = Context({"feedback": feedback})
        self.assertEqual(template.render(context), "Janet Yellin (Leader)")


class TripStage(TestCase):
    @staticmethod
    def _render(trip: models.Trip, *, signups_on_trip: int) -> str:
        template = Template("{% load trip_tags %}{% trip_stage trip signups_on_trip %}")
        context = Context({"trip": trip, "signups_on_trip": signups_on_trip})
        return template.render(context).strip()

    def test_fcfs_open(self):
        trip = factories.TripFactory.create(algorithm="fcfs")

        self.assertEqual(
            self._render(trip, signups_on_trip=0),
            '<span class="label label-success" title="Signups are accepted on a first-come, first-serve basis">Open</span>',
        )

    def test_lottery_open(self):
        trip = factories.TripFactory.create(algorithm="lottery")

        self.assertEqual(
            self._render(trip, signups_on_trip=0),
            '<span class="label label-primary" title="Signups are being accepted and participants will be assigned via lottery.">Lottery</span>',
        )

    @freeze_time("Jan 11 2019 20:30:00 EST")
    def test_not_yet_open(self):
        trip = factories.TripFactory.create(
            signups_open_at=datetime(2019, 1, 13, tzinfo=ZoneInfo("UTC"))
        )

        self.assertEqual(
            self._render(trip, signups_on_trip=0),
            '<span class="label label-info" title="Not yet accepting signups">Open soon</span>',
        )

    def test_full(self):
        trip = factories.TripFactory.create(algorithm="fcfs", maximum_participants=10)

        self.assertEqual(
            self._render(trip, signups_on_trip=10),
            '<span class="label label-warning" title="Trip has no more spaces, but you can join the waitlist">Full</span>',
        )

    def test_closed(self):
        with freeze_time("Jan 11 2019 20:30:00 EST"):
            trip = factories.TripFactory.create()

        with freeze_time("Sep 22 2023 12:30:45 EST"):
            content = self._render(trip, signups_on_trip=10)
        self.assertEqual(
            content,
            '<span class="label label-default" title="No longer accepting signups">Closed</span>',
        )
