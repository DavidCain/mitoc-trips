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
            ["Name", "Date", "Terrain level", "Description", "Leaders"],
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


class TripStageTest(TestCase):
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


class WarnIfEditingApprovedTripTest(TestCase):
    @staticmethod
    def _render(trip: models.Trip) -> str:
        template = Template(
            "{% load trip_tags %}{% warn_if_editing_approved_trip trip %}"
        )
        context = Context({"trip": trip})
        return template.render(context).strip()

    def test_not_approved(self) -> None:
        with freeze_time("2018-01-10"):
            trip = factories.TripFactory.create(
                chair_approved=False,
                trip_date=date(2018, 1, 12),
            )
            rendered = self._render(trip)
        self.assertFalse(rendered.strip())

    def test_approved_but_in_the_past(self) -> None:
        trip = factories.TripFactory.create(
            chair_approved=True,
            trip_date=date(2018, 1, 12),
        )
        with freeze_time("2018-01-13 12:00 UTC"):
            rendered = self._render(trip)
        self.assertFalse(rendered.strip())

    def test_approved_but_no_activity_chair(self) -> None:
        trip = factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            chair_approved=True,
            trip_date=date(2018, 1, 12),
        )
        with freeze_time("2018-01-10 12:00 UTC"):
            rendered = self._render(trip)
        self.assertIn("has been approved", rendered)

        # Simulate a change back to the "None" program:
        trip.program = enums.Program.NONE.value
        with freeze_time("2018-01-10 12:00 UTC"):
            rendered = self._render(trip)
        self.assertFalse(rendered.strip())

    def test_approved_but_no_chair_approval_records(self) -> None:
        with freeze_time("2018-01-10 12:00 UTC"):
            trip = factories.TripFactory.create(
                chair_approved=True,
                trip_date=date(2018, 1, 12),
                program=enums.Program.WINTER_SCHOOL.value,
            )
            self.assertFalse(models.ChairApproval.objects.filter(trip=trip).exists())
            rendered = self._render(trip)
        soup = BeautifulSoup(rendered, "html.parser")
        # We have no idea who the approver was, so we just say the WSC did it.
        self.assertIn(
            "This trip has been approved by the Winter Safety Committee", soup.text
        )

    def test_two_approvers(self) -> None:
        with freeze_time("2026-01-15"):
            trip = factories.TripFactory.create(
                chair_approved=True,
                trip_date=date(2026, 1, 17),
                program=enums.Program.WINTER_SCHOOL.value,
            )
            factories.ChairApprovalFactory.create(
                trip=trip,
                approver__name="First Approver",
            )
            factories.ChairApprovalFactory.create(
                trip=trip,
                approver__name="Second Approver",
            )
            rendered = self._render(trip)
        soup = BeautifulSoup(rendered, "html.parser")
        self.assertIn(
            "This trip has been approved by First Approver and Second Approver",
            soup.text,
        )
        self.assertIn(
            "If making substantial changes, please inform the Winter Safety Committee.",
            soup.text,
        )

    def test_many_approvers(self) -> None:
        with freeze_time("2026-01-15"):
            trip = factories.TripFactory.create(
                chair_approved=True,
                trip_date=date(2026, 1, 17),
                program=enums.Program.WINTER_SCHOOL.value,
            )
            factories.ChairApprovalFactory.create(
                trip=trip,
                approver__name="First Approver",
            )
            factories.ChairApprovalFactory.create(
                trip=trip,
                approver__name="Second Approver",
            )
            factories.ChairApprovalFactory.create(
                trip=trip,
                approver__name="Third Approver",
            )
            rendered = self._render(trip)
        soup = BeautifulSoup(rendered, "html.parser")
        self.assertIn(
            "This trip has been approved by First Approver, Second Approver, and Third Approver",
            soup.text,
        )
        self.assertIn(
            "If making substantial changes, please inform the Winter Safety Committee.",
            soup.text,
        )

    def test_multiple_chair_contacts(self) -> None:
        with freeze_time("2026-08-05"):
            trip = factories.TripFactory.create(
                chair_approved=True,
                trip_date=date(2026, 8, 7),
                program=enums.Program.HIKING.value,
            )
            factories.ChairApprovalFactory.create(
                trip=trip,
                approver__name="Suzie Queue",
            )
            rendered = self._render(trip)
        soup = BeautifulSoup(rendered, "html.parser")
        self.assertIn("This trip has been approved by Suzie Queue", soup.text)
        self.assertIn(
            "If making substantial changes, please inform the 3-season hiking chair and the 3-season Safety Committee.",
            soup.text,
        )
