from datetime import UTC, date, datetime

from bs4 import BeautifulSoup
from django.contrib.auth.models import Group
from django.http.response import HttpResponseBase
from django.test import TestCase
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, models
from ws.tests import factories, strip_whitespace
from ws.utils.itinerary import approve_trip


class TripItineraryViewTest(TestCase):
    VALID_FORM_BODY = {
        "drivers": [],
        "start_location": "At the trailhead.",
        "start_time": "9 am",
        "turnaround_time": "noon",
        "return_time": "3 pm",
        "worry_time": "5 pm",
        "itinerary": "Go up a mountain, then come back",
        # This special extra field is a required affirmation
        "accurate": True,
    }

    def setUp(self):
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)
        self.trip = factories.TripFactory.create(
            program=enums.Program.CLIMBING.value, trip_date=date(2018, 2, 18)
        )

    def _render(
        self, trip_id: int | None = None
    ) -> tuple[HttpResponseBase, BeautifulSoup]:
        response = self.client.get(f"/trips/{trip_id or self.trip.pk}/itinerary/")
        soup = BeautifulSoup(response.content, "html.parser")
        return response, soup

    def test_unauthenticated(self):
        self.client.logout()
        response, _ = self._render()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, f"/accounts/login/?next=/trips/{self.trip.pk}/itinerary/"
        )

    def test_not_leader(self):
        # Normal participants cannot view, but they get a 200 explaining why
        _, soup = self._render()
        self.assertTrue(soup.find("h2", string="Must be a leader to administrate trip"))
        self.assertFalse(soup.find("form"))

    def test_not_leader_on_trip(self):
        _, soup = self._render()
        factories.LeaderRatingFactory.create(
            participant=self.participant, activity=enums.Activity.CLIMBING.value
        )
        self.assertTrue(soup.find("h2", string="Must be a leader to administrate trip"))
        self.assertFalse(soup.find("form"))

    @freeze_time("2018-02-14 12:25:00 EST")
    def test_not_yet_editable(self):
        self.trip.leaders.add(self.participant)

        # Trip is Sunday. On Wednesday, we can't yet edit!
        _, soup = self._render()
        heading = soup.find("h2", string="WIMP information submission")
        par = heading.find_next("p")
        self.assertEqual(
            strip_whitespace(par.text),
            "This form will become available at 6 p.m. on Thursday, Feb 15th.",
        )
        self.assertFalse(soup.find("form"))

        # Submitting does not work!
        resp = self.client.post(
            f"/trips/{self.trip.pk}/itinerary/", self.VALID_FORM_BODY
        )
        self.assertEqual(
            resp.context["form"].errors, {"__all__": ["Itinerary cannot be created"]}
        )
        self.trip.refresh_from_db()
        self.assertIsNone(self.trip.info)

    @freeze_time("2018-02-16 18:45:00 EST")
    def test_currently_editable(self):
        self.trip.leaders.add(self.participant)
        _, soup = self._render()
        par = soup.find("p")
        self.assertEqual(
            strip_whitespace(par.text),
            "This form became available at 6 p.m. on Feb 15, 2018 "
            "and may be edited through the day of the trip (Sunday, Feb 18th).",
        )
        self.assertTrue(soup.find("form"))

        # Posting at this URL creates an itinerary!
        self.assertIsNone(self.trip.info)
        creation_resp = self.client.post(
            f"/trips/{self.trip.pk}/itinerary/", self.VALID_FORM_BODY
        )
        self.assertEqual(creation_resp.status_code, 302)
        self.assertEqual(creation_resp.url, f"/trips/{self.trip.pk}/")

        self.trip.refresh_from_db()
        self.assertIsNotNone(self.trip.info)

    @freeze_time("2018-02-16 18:45:00 EST")
    def test_boating_trip(self) -> None:
        trip = factories.TripFactory.create(
            program=enums.Program.BOATING.value, trip_date=date(2018, 2, 18)
        )
        trip.leaders.add(self.participant)
        _, soup = self._render(trip.pk)
        itinerary = soup.find(id="div_id_itinerary")
        assert itinerary is not None
        self.assertIn("A detailed account of your float plan.", itinerary.text)
        self.assertNotIn("hike", itinerary.text)

    @freeze_time("2018-02-15 08:45:00 EST")
    def test_no_longer_editable(self):
        self.trip.leaders.add(self.participant)

        _, soup = self._render()
        par = soup.find("p")
        self.assertEqual(
            strip_whitespace(par.text),
            "This form will become available at 6 p.m. on Thursday, Feb 15th "
            "and may be edited through the day of the trip (Sunday, Feb 18th).",
        )

        # No longer editable!
        self.assertFalse(soup.find("form"))

        # Submitting does not work!
        resp = self.client.post(
            f"/trips/{self.trip.pk}/itinerary/", self.VALID_FORM_BODY
        )
        self.assertEqual(
            resp.context["form"].errors, {"__all__": ["Itinerary cannot be created"]}
        )
        self.trip.refresh_from_db()
        self.assertIsNone(self.trip.info)


@freeze_time("2020-01-01 12:25:00 EST")
class AllTripsMedicalViewTest(TestCase):
    def setUp(self):
        self.user = factories.UserFactory.create()
        factories.ParticipantFactory.create(user=self.user)
        self.client.force_login(self.user)

    def test_not_the_wimp(self):
        self.assertFalse(perm_utils.in_any_group(self.user, {"WSC", "WIMP"}))
        response = self.client.get("/trips/medical/")
        self.assertEqual(response.status_code, 403)

    def test_no_upcoming_trips(self):
        perm_utils.make_chair(self.user, enums.Activity.WINTER_SCHOOL)
        response = self.client.get("/trips/medical/")
        self.assertFalse(response.context["trips"].exists())

        soup = BeautifulSoup(response.content, "html.parser")

        header = soup.find("h1", string="WIMP Information Sheet")
        self.assertTrue(header)
        self.assertEqual(
            strip_whitespace(header.find_next("p").text),
            "This page contains all known medical information for trips taking place on or after Jan. 1, 2020.",
        )
        self.assertTrue(soup.find("p", string="No upcoming trips."))

    def test_wimp(self):
        Group.objects.get(name="WIMP").user_set.add(self.user)

        # This trip won't be included
        factories.TripFactory.create(name="Old trip", trip_date=date(2019, 12, 25))

        jan3 = factories.TripFactory.create(name="3rd Trip", trip_date=date(2020, 1, 3))
        jan2 = factories.TripFactory.create(name="2nd Trip", trip_date=date(2020, 1, 2))

        response = self.client.get("/trips/medical/")
        self.assertEqual(list(response.context["trips"]), [jan2, jan3])

        soup = BeautifulSoup(response.content, "html.parser")

        # Both trips are described
        self.assertTrue(soup.find("h3", string="2nd Trip"))
        self.assertTrue(soup.find("h3", string="3rd Trip"))

    def test_key_data_present(self):
        Group.objects.get(name="WIMP").user_set.add(self.user)

        leader = factories.ParticipantFactory.create(
            name="Tim Beaver", emergency_info__allergies="Pollen"
        )

        # Write a very robust trip itinerary - we expect that to be surfaced
        plan = "Start at some named trailhead, hike, then come home"
        itinerary = factories.TripInfoFactory.create(itinerary=plan)

        trip = factories.TripFactory.create(
            name="Rad Trip", trip_date=date(2020, 1, 3), info=itinerary
        )
        trip.leaders.add(leader)

        driver = factories.ParticipantFactory.create(
            name="Trip Driver",
            car=factories.CarFactory.create(
                license_plate="559 DKP",
                make="Powell Motors",
                model="Homer",
            ),
        )
        itinerary.drivers.add(driver)

        non_driver = factories.ParticipantFactory.create(name="Non Driver")

        # Put both participants on the trip
        factories.SignUpFactory.create(participant=driver, trip=trip, on_trip=True)
        factories.SignUpFactory.create(participant=non_driver, trip=trip, on_trip=True)
        factories.SignUpFactory.create(
            participant__name="NOT ON TRIP", trip=trip, on_trip=False
        )

        response = self.client.get("/trips/medical/")
        soup = BeautifulSoup(response.content, "html.parser")

        # Both trip participants + the leader are given in the summary
        self.assertTrue(
            soup.find("a", href=f"/participants/{non_driver.pk}/", string="Non Driver")
        )
        self.assertTrue(
            soup.find("a", href=f"/participants/{driver.pk}/", string="Trip Driver")
        )
        self.assertTrue(
            soup.find("a", href=f"/participants/{leader.pk}/", string="Tim Beaver")
        )

        # Signup not on the trip is omitted.
        self.assertFalse(soup.find("a", string="NOT ON TRIP"))

        # Key medical information is given
        self.assertTrue(soup.find("td", string="Pollen"))

        # The driver's car info is given in a table.
        self.assertTrue(soup.find("td", string="559 DKP"))
        self.assertTrue(soup.find("td", string="Powell Motors Homer"))

        # The itinerary of the trip is also given
        self.assertIn(plan, soup.text)


class TripMedicalViewTest(TestCase):
    def setUp(self):
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def _assert_cannot_view(self, trip):
        response = self.client.get(f"/trips/{trip.pk}/medical/")
        soup = BeautifulSoup(response.content, "html.parser")
        self.assertTrue(soup.find("h2", string="Must be a leader to administrate trip"))

    def test_must_have_participant(self):
        self._assert_cannot_view(factories.TripFactory.create())

    def test_participants_cannot_view(self):
        factories.ParticipantFactory.create(user=self.user)
        self._assert_cannot_view(factories.TripFactory.create())

    def test_leader_for_another_trip(self):
        participant = factories.ParticipantFactory.create(user=self.user)
        factories.LeaderRatingFactory.create(
            participant=participant, activity=models.LeaderRating.HIKING
        )

        other_trip = factories.TripFactory.create()
        other_trip.leaders.add(participant)
        trip = factories.TripFactory.create()
        self._assert_cannot_view(trip)

    def test_view_as_leader_with_no_wimp(self):
        trip = factories.TripFactory.create(
            wimp=None, program=enums.Program.HIKING.value
        )

        leader = factories.ParticipantFactory.create(user=self.user)
        factories.LeaderRatingFactory.create(
            participant=leader, activity=models.LeaderRating.HIKING
        )
        trip.leaders.add(leader)
        response = self.client.get(f"/trips/{trip.pk}/medical/")
        soup = BeautifulSoup(response.content, "html.parser")

        self.assertIsNone(trip.wimp)
        self.assertNotEqual(trip.program_enum, enums.Program.WINTER_SCHOOL)
        missing = soup.find(id="wimp-missing")
        self.assertEqual(
            strip_whitespace(missing.text),
            "No WIMP has been assigned to this trip! Set a WIMP?",
        )
        self.assertIsNotNone(missing.find("a", href=f"/trips/{trip.pk}/edit/"))

    def test_view_as_leader_with_wimp_set(self):
        trip = factories.TripFactory.create(
            wimp=factories.ParticipantFactory.create(),
            program=enums.Program.HIKING.value,
        )

        factories.SignUpFactory.create(
            participant__emergency_info__allergies="Bee stings", trip=trip, on_trip=True
        )

        leader = factories.ParticipantFactory.create(user=self.user)
        factories.LeaderRatingFactory.create(
            participant=leader, activity=models.LeaderRating.HIKING
        )
        trip.leaders.add(leader)
        response = self.client.get(f"/trips/{trip.pk}/medical/")
        soup = BeautifulSoup(response.content, "html.parser")

        # This is a non-WS trip with a single WIMP set!
        self.assertIsNotNone(trip.wimp)
        self.assertNotEqual(trip.program_enum, enums.Program.WINTER_SCHOOL)
        self.assertIsNone(soup.find(id="wimp-missing"))

        # Participant medical info is given
        self.assertTrue(soup.find("td", string="Bee stings"))

        # A link for leaders to supply an itinerary is also given
        self.assertTrue(
            soup.find(
                "a",
                href=f"/trips/{trip.pk}/itinerary/",
                string="detailed trip itinerary",
            )
        )

    def test_view_ws_trip_as_wimp(self):
        Group.objects.get(name="WIMP").user_set.add(self.user)
        trip = factories.TripFactory.create(
            wimp=None,
            program=enums.Program.WINTER_SCHOOL.value,
        )

        factories.SignUpFactory.create(
            participant__emergency_info__allergies="Bee stings", trip=trip, on_trip=True
        )

        response = self.client.get(f"/trips/{trip.pk}/medical/")
        soup = BeautifulSoup(response.content, "html.parser")

        # It's a Winter School trip -- we have one WIMP for *all* trips
        self.assertIsNone(trip.wimp_id)
        self.assertIsNone(soup.find(id="wimp-missing"))

        # Participant medical info is given
        self.assertTrue(soup.find("td", string="Bee stings"))

        # The WIMP cannot provide an itinerary, they're not a leader
        self.assertFalse(soup.find("a", href=f"/trips/{trip.pk}/itinerary/"))

    def test_view_as_single_trip_wimp(self):
        wimp = factories.ParticipantFactory.create(user=self.user)
        trip = factories.TripFactory.create(
            wimp=wimp,
            # It's important that this *not* be a WS trip, since it has a WIMP!
            program=enums.Program.HIKING.value,
        )

        factories.SignUpFactory.create(
            participant__emergency_info__allergies="Bee stings", trip=trip, on_trip=True
        )

        response = self.client.get(f"/trips/{trip.pk}/medical/")
        soup = BeautifulSoup(response.content, "html.parser")

        # We of course have a WIMP
        self.assertIsNotNone(trip.wimp_id)
        self.assertIsNone(soup.find(id="wimp-missing"))

        # Participant medical info is given
        self.assertTrue(soup.find("td", string="Bee stings"))

        # The WIMP cannot provide an itinerary, they're not a leader
        self.assertFalse(soup.find("a", href=f"/trips/{trip.pk}/itinerary/"))


@freeze_time("2019-02-15 12:25:00 EST")
class ChairTripViewTest(TestCase):
    def setUp(self):
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def test_no_trip(self):
        response = self.client.get("/climbing/trips/123927341/")
        self.assertEqual(response.status_code, 404)

    def test_redirects_even_if_wrong_activity(self):
        trip = factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            activity=enums.Activity.CLIMBING.value,
            edit_revision=1,
        )
        response = self.client.get(f"/hiking/trips/{trip.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/climbing/trips/{trip.pk}/v1/")

    def test_simple_redirect(self):
        trip = factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            activity=enums.Activity.CLIMBING.value,
            edit_revision=3,
        )
        response = self.client.get(f"/climbing/trips/{trip.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/climbing/trips/{trip.pk}/v3/")


@freeze_time("2019-02-15 12:25:00 EST")
class VersionedChairTripViewTest(TestCase):
    def setUp(self):
        self.participant = factories.ParticipantFactory.create(name="Billy Mays")
        self.user = self.participant.user
        self.client.force_login(self.user)

    @staticmethod
    def _make_climbing_trip(chair_approved=False, **kwargs):
        return factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            activity=enums.Activity.CLIMBING.value,
            chair_approved=chair_approved,
            **kwargs,
        )

    def test_invalid_activity(self):
        trip = self._make_climbing_trip()
        response = self.client.get(f"/curling/trips/{trip.pk}/v37/")
        self.assertEqual(response.status_code, 404)

    def test_must_be_chair(self):
        trip = self._make_climbing_trip(edit_revision=1)
        response = self.client.get(f"/climbing/trips/{trip.pk}/v1/")
        self.assertEqual(response.status_code, 403)

    def test_redirects_to_newer_version(self):
        trip = self._make_climbing_trip(
            chair_approved=False, trip_date=date(2018, 3, 4), edit_revision=2
        )
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        response = self.client.get(f"/climbing/trips/{trip.pk}/v1/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/climbing/trips/{trip.pk}/v2/")

    def test_redirects_from_non_existent_version(self):
        trip = self._make_climbing_trip(
            chair_approved=False, trip_date=date(2018, 3, 4), edit_revision=1
        )
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        response = self.client.get(f"/climbing/trips/{trip.pk}/v234802314/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/climbing/trips/{trip.pk}/v1/")

    def test_view_old_unapproved_trip(self):
        trip = self._make_climbing_trip(
            chair_approved=False, trip_date=date(2018, 3, 4), edit_revision=1
        )

        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        response = self.client.get(f"/climbing/trips/{trip.pk}/v1/")
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, "html.parser")

        # Even though the trip is old, we can still approve it.
        form = soup.find("form", action=".")
        self.assertTrue(form.find("button", string="Approve"))

        # There are no other unapproved trips to navigate between.
        self.assertIsNone(response.context["prev_trip"])
        self.assertIsNone(response.context["next_trip"])

        # Submitting the form approves the trip!
        # Because it's the last one, it goes back to the main listing.
        approve_resp = self.client.post(
            f"/climbing/trips/{trip.pk}/v1/",
            {"notes": "", "trip": trip.pk, "trip_edit_revision": 1},
        )
        self.assertEqual(approve_resp.status_code, 302)
        self.assertEqual(approve_resp.url, "/climbing/trips/")

    def test_view_old_approved_trip(self):
        trip = self._make_climbing_trip(trip_date=date(2018, 3, 4), edit_revision=42)
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        approve_trip(trip, approving_chair=self.participant, trip_edit_revision=42)

        response = self.client.get(f"/climbing/trips/{trip.pk}/v42/")
        self.assertEqual(response.status_code, 200)

        soup = BeautifulSoup(response.content, "html.parser")

        # There's no approval form, just an indicator that it's approved
        self.assertFalse(soup.find("form", action="."))
        approved = soup.find("button", string="Approved!")
        self.assertTrue(approved)
        self.assertEqual(
            approved.attrs["uib-tooltip"],
            "by Billy Mays Feb. 15, 2019, 12:25 p.m.",
        )

    def test_upcoming_trips(self):
        # Make each of these the same trip type, so we sort just by date
        four = self._make_climbing_trip(
            trip_date=date(2019, 3, 4),
            trip_type=enums.TripType.BOULDERING.value,
            edit_revision=5,
        )
        two = self._make_climbing_trip(
            trip_date=date(2019, 3, 2),
            trip_type=enums.TripType.BOULDERING.value,
            edit_revision=37,
        )
        three = self._make_climbing_trip(
            trip_date=date(2019, 3, 3),
            trip_type=enums.TripType.BOULDERING.value,
        )
        one = self._make_climbing_trip(
            trip_date=date(2019, 3, 1),
            trip_type=enums.TripType.BOULDERING.value,
        )

        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        # "Next" and "previous" are in chronological order!
        response = self.client.get(f"/climbing/trips/{two.pk}/v37/")
        self.assertEqual(response.context["prev_trip"], one)
        self.assertEqual(response.context["next_trip"], three)

        # Because we have a next trip, the button to approve it links to "& next"
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", action=".")
        self.assertTrue(form.find("button", string="Approve & Next"))

        # Also, next and previous only navigate between unapproved trips
        three.chair_approved = True
        three.save()
        response = self.client.get(f"/climbing/trips/{two.pk}/v37/")
        self.assertEqual(response.context["prev_trip"], one)
        self.assertEqual(response.context["next_trip"], four)

        # Finally, approving a trip brings us straight to the page for the next.
        self.assertIs(two.chair_approved, False)
        self.assertFalse(models.ChairApproval.objects.exists())
        approve_resp = self.client.post(
            f"/climbing/trips/{two.pk}/v37/",
            {"notes": "", "trip": two.pk, "trip_edit_revision": 37},
        )
        self.assertEqual(approve_resp.status_code, 302)
        self.assertEqual(approve_resp.url, f"/climbing/trips/{four.pk}/v5/")
        two.refresh_from_db()
        approval = models.ChairApproval.objects.get()
        self.assertEqual(approval.trip, two)
        self.assertEqual(
            approval.time_created,
            datetime(2019, 2, 15, 17, 25, tzinfo=UTC),
        )
        self.assertEqual(approval.approver, self.participant)
        self.assertIs(two.chair_approved, True)

        # The last trip in the series has no "next" button
        resp = self.client.get(approve_resp.url)
        self.assertEqual(resp.context["prev_trip"], one)
        self.assertIsNone(resp.context["next_trip"])

    def test_no_navigation_between_old_trips(self):
        trip = self._make_climbing_trip(
            chair_approved=False,
            trip_date=date(2018, 3, 4),
            edit_revision=64,
        )
        self._make_climbing_trip(chair_approved=False, trip_date=date(2018, 3, 3))
        self._make_climbing_trip(chair_approved=False, trip_date=date(2018, 3, 5))

        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        response = self.client.get(f"/climbing/trips/{trip.pk}/v64/")
        self.assertEqual(response.status_code, 200)

        # We don't prompt the chair to approve other old trips.
        self.assertIsNone(response.context["prev_trip"])
        self.assertIsNone(response.context["next_trip"])
