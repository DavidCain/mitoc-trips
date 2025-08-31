import re
from datetime import date

from bs4 import BeautifulSoup
from django.test import Client, TestCase
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, models
from ws.tests import factories, strip_whitespace


class Helpers:
    client: Client

    @staticmethod
    def _form_data(form):
        for elem in form.find_all("textarea"):
            yield elem["name"], elem.text

        for elem in form.find_all("input"):
            if elem["type"] == "checkbox" and elem.get("checked") is not None:
                yield elem["name"], "on"
            else:
                yield elem["name"], elem.get("value", "")

        for select in form.find_all("select"):
            selection = select.find("option", selected=True)
            value = selection["value"] if selection else ""
            yield select["name"], value

    def _get(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, "html.parser")
        return response, soup

    @staticmethod
    def _expect_title(soup, expected):
        title = strip_whitespace(soup.title.string)
        assert title == f"{expected} | MITOC Trips"

    @staticmethod
    def _expect_past_trips(response, expected_trip_pks):
        assert expected_trip_pks == [trip.pk for trip in response.context["past_trips"]]

    @staticmethod
    def _expect_current_trips(response, expected_trip_pks):
        assert [
            trip.pk for trip in response.context["current_trips"]
        ] == expected_trip_pks

    @staticmethod
    def _expect_upcoming_header(soup, expected_text):
        """Expect a text label on the header, plus the subscribe+digest buttons."""
        header = soup.body.find("h3")
        header_text = strip_whitespace(header.get_text())
        # There is an RSS button and a weekly email digest button included in the header
        assert header_text == f"{expected_text} RSS Weekly digest"

    @staticmethod
    def _expect_link_for_date(soup, datestring):
        link = soup.find("a", href=f"/trips/?after={datestring}")
        assert link.get_text(strip=True) == "Previous trips"


@freeze_time("2019-02-15 12:25:00 EST")
class TripListViewTest(TestCase, Helpers):
    def test_upcoming_trips_without_filter(self):
        """With no default filter, we only show upcoming trips."""
        response, soup = self._get("/trips/")
        # We don't bother rendering any past trips
        self.assertNotIn("past_trips", response.context)
        self._expect_title(soup, "Upcoming trips")
        # We just say 'Upcoming trips' (no mention of date)
        self._expect_upcoming_header(soup, "Upcoming trips")

    def test_invalid_filter(self):
        """When an invalid date is passed, we just ignore it."""
        # Make two trips that are in the future, but before the requested cutoff
        factories.TripFactory.create(trip_date="2019-02-28")
        factories.TripFactory.create(trip_date="2019-02-27")

        # Ask for upcoming trips after an invalid future date
        response, soup = self._get("/trips/?after=2019-02-31")

        # We warn the user that this date was invalid.
        warning = soup.find(class_="alert alert-danger")
        self.assertTrue(response.context["date_invalid"])
        self.assertIn("Invalid date", warning.get_text())

        # However, we still return results (behaving as if no date filter was given)
        # We don't include past trips, though, since the `after` cutoff was invalid
        # (We only show upcoming trips)
        self._expect_title(soup, "Upcoming trips")
        self.assertNotIn("past_trips", response.context)
        # We use today's date for the 'previous trips' link
        self._expect_link_for_date(soup, "2018-02-15")

    @freeze_time("2018-01-10 12:25:00 EST")
    def test_trips_with_filter(self):
        """We support filtering the responded list of trips."""
        # Need to log in to see old trips
        self.client.force_login(factories.UserFactory.create())

        # Make a very old trip that will not be in our filter
        factories.TripFactory.create(trip_date="2016-12-23")

        # Make trips that are in the past, but *after* the queried date
        one_week_ago = factories.TripFactory.create(trip_date="2018-01-03")
        one_month_ago = factories.TripFactory.create(trip_date="2017-12-09")

        # Make some upcoming trips
        trip1 = factories.TripFactory.create(trip_date="2018-01-14")
        trip2 = factories.TripFactory.create(trip_date="2018-04-22")
        trip3 = factories.TripFactory.create(trip_date="2018-04-25")

        # Filter based on a date in the past
        response, soup = self._get("/trips/?after=2017-11-15")
        self.assertFalse(response.context["date_invalid"])

        # Observe that we have an 'Upcoming trips' section, plus a section for past trips
        self._expect_upcoming_header(soup, "Upcoming trips")
        self._expect_title(soup, "Trips after 2017-11-15")
        # Upcoming trips are sorted such that the next-occurring trips are on top
        self._expect_current_trips(response, [trip1.pk, trip2.pk, trip3.pk])

        # Old trips are displayed in the *opposite* order, most recent on top
        self._expect_past_trips(response, [one_week_ago.pk, one_month_ago.pk])
        self._expect_link_for_date(soup, "2016-11-15")

    def trips_after_first_trip_date(self):
        """We don't show 'Previous trips' before the first trip."""
        trip = factories.TripFactory.create(name="Tecumseh", trip_date="2015-01-10")

        # Filter based on a date in the past
        response, soup = self._get("/trips/?after=2015-01-10")
        self.assertFalse(response.context["date_invalid"])

        self._expect_title(soup, "Trips after 2015-01-10")
        self._expect_past_trips(response, [trip.pk])

        self.assertIsNone(soup.find(string="Previous trips"))

    def test_trips_with_very_early_date(self):
        """Authed users can ask for trips starting after the year 1."""
        self.client.force_login(factories.UserFactory.create())

        trip = factories.TripFactory.create(trip_date="2016-12-23")

        # Filter based on a date in the past
        response, soup = self._get("/trips/?after=0001-10-17")
        self.assertFalse(response.context["date_invalid"])

        self._expect_title(soup, "Trips after 0001-10-17")
        self._expect_past_trips(response, [trip.pk])

        self.assertIsNone(soup.find(string="Previous trips"))

    def test_upcoming_trips_can_be_filtered(self):
        """If supplying an 'after' date in the future, that still permits filtering!"""
        _next_week = factories.TripFactory.create(trip_date="2019-02-22")
        next_month = factories.TripFactory.create(trip_date="2019-03-22")
        next_year = factories.TripFactory.create(trip_date="2020-02-05")
        response, soup = self._get("/trips/?after=2019-03-15")
        self._expect_link_for_date(soup, "2018-03-15")

        # We remove the RSS + email buttons
        header = soup.body.find("h3")
        self.assertEqual(strip_whitespace(header.text), "Trips after Mar 15, 2019")

        # The trip next month & year is included, but not next week.
        # Per usual, the next-upcoming trips are shown first!
        self._expect_current_trips(response, [next_month.pk, next_year.pk])


class AnonymousTripListViewTest(TestCase, Helpers):
    @freeze_time("2024-06-25 12:45:59 EDT")
    def test_custom_recent_trips(self):
        """Anonymous users can view any date in the last 365 days."""
        this_year = factories.TripFactory.create(trip_date="2024-02-02")
        factories.TripFactory.create(trip_date="2023-12-25")

        response, soup = self._get("/trips/?after=2024-01-01")
        self.assertIs(response.context["must_login_to_view_older_trips"], False)

        self._expect_past_trips(response, [this_year.pk])
        # We don't offer to go back an extra 365 days, just to the cutoff
        self._expect_link_for_date(soup, "2023-06-26")

    @freeze_time("2024-06-25 12:45:59 EDT")
    def test_lookback_to_earliest_date(self):
        """We support lookback up to 365 days."""
        within_window = factories.TripFactory.create(trip_date="2023-07-07")
        factories.TripFactory.create(trip_date="2023-01-02")

        response, soup = self._get("/trips/?after=2023-06-26")
        self.assertIs(response.context["must_login_to_view_older_trips"], True)

        self._expect_past_trips(response, [within_window.pk])
        link = soup.find("a", href="/accounts/login/?next=/trips/?after=2022-06-26")
        self.assertEqual(link.get_text(strip=True), "Log in to view previous trips")

    @freeze_time("2024-06-25 12:45:59 EDT")
    def test_lookback_too_old(self):
        factories.TripFactory.create(trip_date="2023-07-07")
        response, soup = self._get("/trips/?after=2016-01-12")

        # Even though there *is* a trip that's viewable, we hide it.
        # If anybody's writing a parser or similar, we don't want to mislead.
        # (Showing *some* past trips in response to an invalid request is unwise)
        self.assertNotIn("past_trips", response.context)
        self.assertIsNone(soup.find(string="Previous trips"))

        alert = soup.find(class_="alert-danger")
        self.assertEqual(
            strip_whitespace(alert.text),
            "You must log in to view trips before 2023-06-26.",
        )
        self.assertEqual(
            alert.find("a").attrs,
            {"href": "/accounts/login/?next=%2Ftrips%2F%3Fafter%3D2016-01-12"},
        )

        # The footer links to another 365 days back, just for consistency
        link = soup.find("a", href="/accounts/login/?next=/trips/?after=2015-01-12")
        self.assertEqual(link.get_text(strip=True), "Log in to view previous trips")

    @freeze_time("2024-06-25 12:45:59 EDT")
    def test_lookup_before_first_trip(self):
        factories.TripFactory.create(trip_date="2023-07-07")
        response, soup = self._get("/trips/?after=2010-07-20")

        # Even though there *is* a trip that's viewable, we hide it.
        # If anybody's writing a parser or similar, we don't want to mislead.
        # (Showing *some* past trips in response to an invalid request is unwise)
        self.assertNotIn("past_trips", response.context)
        self.assertIsNone(soup.find(string="Previous trips"))

        alert = soup.find(class_="alert-danger")
        self.assertEqual(
            strip_whitespace(alert.text),
            "You must log in to view trips before 2023-06-26.",
        )
        self.assertEqual(
            alert.find("a").attrs,
            {"href": "/accounts/login/?next=%2Ftrips%2F%3Fafter%3D2010-07-20"},
        )

        # Even if logged in, we couldn't show older trips!
        self.assertIsNone(soup.find(string="Log in to view previous trips"))


class AllTripsViewTest(TestCase):
    def test_simple_redirect(self):
        response = self.client.get("/trips/all/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/trips/")


class CreateTripViewTest(TestCase, Helpers):
    @freeze_time("2019-12-15 12:25:00 EST")
    def test_superuser_can_create_any_program(self):
        """Even though it's not IAP, the superuser can make any trip type."""
        user = factories.UserFactory.create(is_superuser=True)
        factories.ParticipantFactory.create(user_id=user.pk)
        self.client.force_login(user)
        _resp, soup = self._get("/trips/create/")
        options = soup.find("select", attrs={"name": "program"}).find_all("option")
        self.assertCountEqual(
            [opt["value"] for opt in options],
            [program.value for program in enums.Program],
        )

    @freeze_time("2022-01-24 12:25:00 EST")
    def test_winter_school_is_default_during_iap(self):
        """For simplicity, we assume that new trips in IAP are in the WS program."""
        leader = factories.ParticipantFactory.create()
        factories.LeaderRatingFactory.create(
            participant=leader, activity=models.LeaderRating.WINTER_SCHOOL
        )
        self.client.force_login(leader.user)
        _resp, soup = self._get("/trips/create/")
        select = soup.find("select", attrs={"name": "program"})
        self.assertEqual(
            [opt.text for opt in select.find_all("option")],
            ["Winter School", "Winter (outside IAP)", "Circus", "Service", "None"],
        )
        ws_option = select.find("option", value=enums.Program.WINTER_SCHOOL.value)
        self.assertIn("selected", ws_option.attrs)

    @freeze_time("2019-12-15 12:25:00 EST")
    def test_winter_school_not_available_outside_iap(self):
        """Normal trip leaders can only make normal winter trips outside IAP."""
        leader = factories.ParticipantFactory.create()
        factories.LeaderRatingFactory.create(
            participant=leader, activity=models.LeaderRating.WINTER_SCHOOL
        )
        self.client.force_login(leader.user)
        _resp, soup = self._get("/trips/create/")
        select = soup.find("select", attrs={"name": "program"})

        winter_option = select.find("option", value=enums.Program.WINTER_NON_IAP.value)
        self.assertIn("selected", winter_option.attrs)

        programs = [opt["value"] for opt in select.find_all("option")]
        self.assertNotIn(enums.Program.WINTER_SCHOOL.value, programs)

    def test_creation(self):
        """End-to-end test of form submission on creating a new trip.

        This is something of an integration test. Dealing with forms
        in this way is a bit of a hassle, but this ensures that we're handling
        everything properly.

        More specific behavior testing should be done at the form level.
        """
        user = factories.UserFactory.create()
        self.client.force_login(user)
        trip_leader = factories.ParticipantFactory.create(user=user)
        factories.LeaderRatingFactory.create(
            participant=trip_leader, activity=models.LeaderRating.BIKING
        )
        _resp, soup = self._get("/trips/create/")
        form = soup.find("form")
        form_data = dict(self._form_data(form))

        # We have the selections pre-populated too.
        self.assertEqual(form_data["program"], enums.Program.BIKING.value)
        self.assertEqual(form_data["algorithm"], "lottery")

        # Fill in the form with some blank, but required values (accept the other defaults)
        form_data.update(
            {
                "name": "My Great Trip",
                "trip_type": enums.TripType.MOUNTAIN_BIKING.value,
                "difficulty_rating": "Intermediate",
                "description": "Join us on Mt Tam for a grand old time",
                "summary": "Let's go biking!",
            }
        )
        self.assertEqual(form["action"], ".")

        # Upon form submission, we're redirected to the new trip's page!
        resp = self.client.post("/trips/create/", form_data, follow=False)
        self.assertEqual(resp.status_code, 302)
        new_trip_url = re.compile(r"^/trips/(\d+)/$")
        self.assertRegex(resp.url, new_trip_url)
        match = new_trip_url.match(resp.url)
        assert match is not None
        trip_pk = int(match.group(1))

        trip = models.Trip.objects.get(pk=trip_pk)
        self.assertEqual(trip.creator, trip_leader)
        self.assertEqual(trip.last_updated_by, trip_leader)
        self.assertEqual(trip.edit_revision, 1)
        self.assertEqual(trip.name, "My Great Trip")
        self.assertEqual(trip.summary, "Let's go biking!")

    def test_creation_without_summary(self):
        user = factories.UserFactory.create()
        self.client.force_login(user)
        trip_leader = factories.ParticipantFactory.create(user=user)
        factories.LeaderRatingFactory.create(
            participant=trip_leader, activity=models.LeaderRating.BIKING
        )
        _resp, soup = self._get("/trips/create/")
        form = soup.find("form")
        form_data = dict(self._form_data(form))

        # Fill in the form with some blank, but required values (accept the other defaults)
        form_data.update(
            {
                "name": "Biking at Mt Tam",
                "trip_type": enums.TripType.MOUNTAIN_BIKING.value,
                "difficulty_rating": "Intermediate",
                "description": "\n".join(
                    [
                        "## What is Mt Tam?",
                        "Mt Tam is the *birthplace of mountain biking*, located in the San Francisco Bay.",
                        "",
                        "## How awesome will this be?",
                        "**Very awesome**.",
                    ]
                ),
            }
        )
        self.assertEqual(form["action"], ".")

        self.client.post("/trips/create/", form_data)

        trip = models.Trip.objects.order_by("id").last()
        self.assertEqual(
            trip.summary,
            "What is Mt Tam? Mt Tam is the birthplace of mountain biking, located in the S...",
        )


class EditTripViewTest(TestCase, Helpers):
    def test_superusers_may_edit_trip_without_required_activity(self):
        admin = factories.UserFactory.create(is_superuser=True)
        self.client.force_login(admin)

        trip = factories.TripFactory.create(program=enums.Program.SERVICE.value)
        self.assertIsNone(trip.required_activity_enum())

        _edit_resp, soup = self._get(f"/trips/{trip.pk}/edit/")
        self.assertTrue(soup.find("form"))

    def test_leaders_cannot_edit_other_leaders_trip(self):
        leader = factories.ParticipantFactory.create()
        factories.LeaderRatingFactory.create(
            participant=leader, activity=models.LeaderRating.CLIMBING
        )
        self.client.force_login(leader.user)

        trip = factories.TripFactory.create(
            name="Rad Trip", program=enums.Program.CLIMBING.value
        )

        _edit_resp, soup = self._get(f"/trips/{trip.pk}/edit/")
        self.assertTrue(soup.find("h2", string="Must be a leader to administrate trip"))
        self.assertFalse(soup.find("form"))

    @freeze_time("2022-01-15 12:25:00 EST")
    def test_editing_old_trip(self):
        leader = factories.ParticipantFactory.create()
        self.client.force_login(leader.user)

        # It doesn't matter that they created the trip, they still cannot edit!
        trip = factories.TripFactory.create(
            creator=leader,
            trip_date=date(2021, 12, 10),
            program=enums.Program.CLIMBING.value,
        )
        trip.leaders.add(leader)

        _edit_resp, soup = self._get(f"/trips/{trip.pk}/edit/")
        self.assertTrue(
            soup.find("h2", string="Only activity chairs or admins can edit old trips")
        )
        self.assertIsNone(soup.find("form"))

        # However, activity chairs can still edit!
        chair = factories.ParticipantFactory.create()
        perm_utils.make_chair(chair.user, enums.Activity.CLIMBING)
        self.client.force_login(chair.user)
        _edit_resp, chair_soup = self._get(f"/trips/{trip.pk}/edit/")
        self.assertTrue(chair_soup.find("form"))

    @freeze_time("2022-01-15 12:25:00 EST")
    def test_editing_non_ws_trip_during_iap(self):
        """Existing trips, which are not WS, don't have the program enum changed.

        This test ensures that we don't accidentally change an existing trip's program,
        due to logic which is meant to default a *new* trip to being WS during IAP.
        """
        leader = factories.ParticipantFactory.create()
        self.client.force_login(leader.user)
        factories.LeaderRatingFactory.create(
            participant=leader, activity=models.LeaderRating.WINTER_SCHOOL
        )
        trip = factories.TripFactory.create(
            creator=leader, program=enums.Program.NONE.value
        )
        trip.leaders.add(leader)
        _edit_resp, soup = self._get(f"/trips/{trip.pk}/edit/")

        select = soup.find("select", attrs={"name": "program"})
        # WS is given as an *option* for this trip, but not selected
        self.assertIn("Winter School", [opt.text for opt in select.find_all("option")])
        # The existing trip's program is selected
        ws_option = select.find("option", value=enums.Program.NONE.value)
        self.assertIn("selected", ws_option.attrs)

    def test_editing(self):
        user = factories.UserFactory.create(email="leader@example.com")
        self.client.force_login(user)
        trip_creator = factories.ParticipantFactory.create(user=user)
        factories.LeaderRatingFactory.create(
            participant=trip_creator, activity=models.LeaderRating.WINTER_SCHOOL
        )
        trip = factories.TripFactory.create(
            creator=trip_creator, program=enums.Program.WINTER_SCHOOL.value
        )
        trip.leaders.add(trip_creator)

        # Add an old leader to this trip, to demonstrate that editing & submitting is allowed
        old_leader = factories.ParticipantFactory.create()
        factories.LeaderRatingFactory.create(
            participant=old_leader,
            activity=models.LeaderRating.WINTER_SCHOOL,
            active=False,
        )
        trip.leaders.add(old_leader)

        _edit_resp, soup = self._get(f"/trips/{trip.pk}/edit/")
        form = soup.find("form")
        form_data = dict(self._form_data(form))

        # We supply the two leaders via an Angular directive
        # (Angular will be used to populate the `leaders` input, so manually populate here)
        self.assertEqual(
            soup.find("leader-select")["leader-ids"],
            f"[{trip_creator.pk}, {old_leader.pk}]",
        )
        form_data["leaders"] = [trip_creator.pk, old_leader.pk]

        # We have the selections pre-populated with existing data
        self.assertEqual(form_data["program"], enums.Program.WINTER_SCHOOL.value)
        self.assertEqual(form_data["algorithm"], "lottery")

        # Make some updates to the trip!
        form_data.update({"name": "An old WS trip"})
        self.assertEqual(form["action"], ".")

        # Upon form submission, we're redirected to the new trip's page!
        resp = self.client.post(f"/trips/{trip.pk}/edit/", form_data, follow=False)
        self.assertEqual(resp.status_code, 302)

        trip = models.Trip.objects.get(pk=trip.pk)
        self.assertEqual(trip.creator, trip_creator)
        self.assertCountEqual(trip.leaders.all(), [old_leader, trip_creator])
        self.assertEqual(trip.name, "An old WS trip")

        # To support any legacy behavior still around, we set activity.
        self.assertEqual(trip.activity, "winter_school")

    @freeze_time("2019-02-15 12:25:00 EST")
    def test_update_rescinds_approval(self):
        leader = factories.ParticipantFactory.create()
        self.client.force_login(leader.user)
        factories.LeaderRatingFactory.create(
            participant=leader, activity=enums.Activity.CLIMBING.value
        )
        trip = factories.TripFactory.create(
            creator=leader,
            program=enums.Program.CLIMBING.value,
            trip_date=date(2019, 3, 2),
            chair_approved=True,
        )

        edit_resp, soup = self._get(f"/trips/{trip.pk}/edit/")
        self.assertTrue(edit_resp.context["update_rescinds_approval"])

        form = soup.find("form")
        form_data = dict(self._form_data(form))

        self.assertEqual(
            strip_whitespace(soup.find(class_="alert-warning").text),
            "This trip has been approved by the activity chair. "
            "Making any changes will rescind this approval.",
        )

        # Upon form submission, we're redirected to the new trip's page!
        resp = self.client.post(f"/trips/{trip.pk}/edit/", form_data, follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f"/trips/{trip.pk}/")

        # We can see that chair approval is now removed.
        trip = models.Trip.objects.get(pk=trip.pk)
        self.assertFalse(trip.chair_approved)

    @freeze_time("2019-02-15 12:25:00 EST")
    def test_updates_on_stale_trips(self):
        leader = factories.ParticipantFactory.create()
        self.client.force_login(leader.user)
        factories.LeaderRatingFactory.create(
            participant=leader, activity=enums.Activity.CLIMBING.value
        )
        trip = factories.TripFactory.create(
            edit_revision=0,
            creator=leader,
            program=enums.Program.CLIMBING.value,
            winter_terrain_level=None,
            trip_date=date(2019, 3, 2),
        )

        # Simulate a stale page content by loading data *first*
        _edit_resp, initial_soup = self._get(f"/trips/{trip.pk}/edit/")
        form_data = dict(self._form_data(initial_soup.find("form")))

        # (Pretend that two others have updated edited the trip)
        trip.edit_revision += 2
        trip.leaders.add(factories.ParticipantFactory.create())
        trip.description = "Other edits changed this description!"
        trip.last_updated_by = factories.ParticipantFactory.create(name="Joe Schmoe")
        trip.save()

        resp = self.client.post(f"/trips/{trip.pk}/edit/", form_data, follow=False)
        soup = BeautifulSoup(resp.content, "html.parser")
        warning = strip_whitespace(soup.find(class_="alert alert-danger").text)
        self.assertIn(
            "This trip has already been edited 2 times, most recently by Joe Schmoe.",
            warning,
        )
        self.assertIn(
            "To make updates to the trip, please load the page again.", warning
        )
        self.assertIn("Fields which differ: Leaders, Description", warning)

        # No edit was made; we have form errors
        trip.refresh_from_db()
        self.assertEqual(trip.edit_revision, 2)


class DeleteTripViewTest(TestCase, Helpers):
    def test_cannot_get(self):
        """Supporting GET would let attackers embed "images" and such."""
        participant = factories.ParticipantFactory.create()
        self.client.force_login(participant.user)

        trip = factories.TripFactory.create(creator=participant)

        resp = self.client.get(f"/trips/{trip.pk}/delete/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f"/trips/{trip.pk}/")

    def test_can_delete_your_own_trip(self):
        participant = factories.ParticipantFactory.create()
        self.client.force_login(participant.user)

        trip = factories.TripFactory.create(creator=participant)

        resp = self.client.post(f"/trips/{trip.pk}/delete/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/trips/")
        self.assertFalse(models.Trip.objects.filter(pk=trip.pk).exists())

    def test_cannot_delete_old_trips(self):
        participant = factories.ParticipantFactory.create()
        self.client.force_login(participant.user)

        trip = factories.TripFactory.create(
            creator=participant,
            trip_date=date(2020, 2, 5),
        )
        with freeze_time("2020-03-12 12:25:00 EST"):
            resp = self.client.post(f"/trips/{trip.pk}/delete/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(models.Trip.objects.filter(pk=trip.pk).exists())


class SearchTripsViewTest(TestCase):
    def setUp(self):
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def test_login_required(self):
        self.client.logout()
        resp = self.client.get("/trips/search/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/accounts/login/?next=/trips/search/")

    def test_initial_page_load_no_trips(self):
        factories.TripFactory.create()
        soup = BeautifulSoup(self.client.get("/trips/search/").content, "html.parser")
        self.assertIsNone(soup.find("table"))

    def test_no_results_from_text_search(self):
        factories.TripFactory.create()
        soup = BeautifulSoup(
            self.client.get("/trips/search/?q=Paintball").content, "html.parser"
        )
        self.assertIsNone(soup.find("table"))
        self.assertIn("No matching trips!", soup.text)

    def test_no_results_from_filters(self):
        factories.TripFactory.create(program=enums.Program.CLIMBING.value)
        soup = BeautifulSoup(
            self.client.get("/trips/search/?program=hiking").content, "html.parser"
        )
        self.assertIsNone(soup.find("table"))
        self.assertIn("No matching trips!", soup.text)

    def test_empty_post_redirects(self):
        """Posting an empty form is valid, but we warn about it."""
        resp = self.client.post("/trips/search/", follow=True)
        self.assertIn(b"Specify a search query and/or some filters", resp.content)

    def test_search_redirects_to_get(self):
        """To show users that search works with GET, we just redirect."""
        resp = self.client.post(
            "/trips/search/", {"q": "Frankenstein", "program": "climbing"}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/trips/search/?q=Frankenstein&program=climbing")

    def test_free_text_search(self):
        """We support full-text search on trips."""
        # Create three trips -- only two contain 'Frankenstein'
        factories.TripFactory.create(name="Blue Hills", description="Let's hike!")
        factories.TripFactory.create(name="Frankenstein Cliffs", description="Woo ice")
        factories.TripFactory.create(
            name="Leader social",
            # Note that the vector can make sense of "Frankenstein's"
            description="Eat so much ice cream your stomach will sound like Frankenstein's monster.",
        )
        soup = BeautifulSoup(
            self.client.get("/trips/search/?q=Frankenstein").content,
            "html.parser",
        )
        table = soup.find("table").find("tbody")
        trips = table.find_all("tr")
        self.assertEqual(
            [trip.find("a").text.strip() for trip in trips],
            # "Frankenstein" in the title weights it first
            ["Frankenstein Cliffs", "Leader social"],
        )

    def test_filters_only(self):
        """We can search for trips with *only* filters, and no search query."""
        factories.TripFactory.create(name="Franconia Ridge", winter_terrain_level="C")
        factories.TripFactory.create(name="Mt. Washington", winter_terrain_level="C")
        factories.TripFactory.create(
            name="Washington ice",
            winter_terrain_level="C",
            trip_type=enums.TripType.ICE_CLIMBING.value,
        )
        factories.TripFactory.create(
            name="Non WS trip",
            program=enums.Program.CLIMBING.value,
        )

        soup = BeautifulSoup(
            self.client.get(
                "/trips/search/?winter_terrain_level=C&trip_type=climbing_ice"
            ).content,
            "html.parser",
        )
        table = soup.find("table").find("tbody")
        trips = table.find_all("tr")
        self.assertEqual(
            [trip.find("a").text.strip() for trip in trips],
            ["Washington ice"],
        )

    def test_search_and_filters_only(self):
        """We can search using a query and some filters."""
        # Couple B trips, couple ice trips, but only one B Ice trip
        factories.TripFactory.create(
            name="New Hampshire Franconia Ridge",
            winter_terrain_level="B",
            trip_type=enums.TripType.HIKING.value,
        )
        factories.TripFactory.create(
            name="New Hampshire Frankenstein ice",
            winter_terrain_level="B",
            trip_type=enums.TripType.ICE_CLIMBING.value,
        )
        factories.TripFactory.create(
            name="New Hampshire Mt. Washington",
            winter_terrain_level="C",
            trip_type=enums.TripType.HIKING.value,
        )
        factories.TripFactory.create(
            name="New Hampshire Washington ice",
            winter_terrain_level="C",
            trip_type=enums.TripType.ICE_CLIMBING.value,
        )
        factories.TripFactory.create(
            name="Non WS trip",
            program=enums.Program.CLIMBING.value,
        )

        # First show that we match all the trips by search "Hampshire" *only*
        rows_from_search_only = (
            BeautifulSoup(
                self.client.get("/trips/search/?q=Hampshire").content,
                "html.parser",
            )
            .find("table")
            .find("tbody")
            .find_all("tr")
        )
        self.assertCountEqual(
            [trip.find("a").text.strip() for trip in rows_from_search_only],
            {
                "New Hampshire Franconia Ridge",
                "New Hampshire Frankenstein ice",
                "New Hampshire Mt. Washington",
                "New Hampshire Washington ice",
            },
        )

        # Finally, we can filter to BI trips in New Hampshire -- we get just the one!
        soup = BeautifulSoup(
            self.client.get(
                "/trips/search/?q=Hampshire&winter_terrain_level=B&trip_type=climbing_ice"
            ).content,
            "html.parser",
        )
        rows = soup.find("table").find("tbody").find_all("tr")
        self.assertEqual(
            [trip.find("a").text.strip() for trip in rows],
            ["New Hampshire Frankenstein ice"],
        )


class ApproveTripsViewTest(TestCase):
    def setUp(self):
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    @staticmethod
    def _make_climbing_trip(chair_approved=False, **kwargs):
        return factories.TripFactory.create(
            program=enums.Program.CLIMBING.value,
            activity=enums.Activity.CLIMBING.value,
            chair_approved=chair_approved,
            **kwargs,
        )

    def test_unauthenticated(self):
        self.client.logout()
        response = self.client.get("/climbing/trips/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/?next=/climbing/trips/")

    def test_not_an_activity_chair(self):
        response = self.client.get("/climbing/trips/")
        self.assertEqual(response.status_code, 403)

    def test_bad_activity(self):
        response = self.client.get("/snowmobiling/trips/")
        self.assertEqual(response.status_code, 404)

    def test_no_trips_found(self):
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        response = self.client.get("/climbing/trips/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["trips_needing_approval"], [])
        self.assertIsNone(response.context["first_unapproved_trip"])

    def test_all_trips_approved(self):
        self._make_climbing_trip(chair_approved=True)
        self._make_climbing_trip(chair_approved=True)
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        response = self.client.get("/climbing/trips/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["trips_needing_approval"], [])
        self.assertIsNone(response.context["first_unapproved_trip"])

    def test_terrain_level_column(self):
        """The "terrain level" column only appears for activity chairs."""
        self._make_climbing_trip(chair_approved=True)
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        soup = BeautifulSoup(self.client.get("/climbing/trips/").content, "html.parser")
        self.assertFalse(soup.find("th", string="Terrain level"))

        perm_utils.make_chair(self.user, enums.Activity.WINTER_SCHOOL)
        factories.TripFactory.create(program=enums.Program.WINTER_SCHOOL.value)
        ws_soup = BeautifulSoup(
            self.client.get("/winter_school/trips/").content, "html.parser"
        )
        self.assertTrue(ws_soup.find("th", string="Terrain level"))

    def test_chair(self):
        self._make_climbing_trip(chair_approved=True)
        unapproved = factories.TripFactory.create(
            program=enums.Program.SCHOOL_OF_ROCK.value,
            activity=enums.Activity.CLIMBING.value,
            chair_approved=False,
        )
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        response = self.client.get("/climbing/trips/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["first_unapproved_trip"], unapproved)

    @freeze_time("2019-07-05 12:25:00 EST")
    def test_past_unapproved_trips_ignored(self):
        """We only prompt chairs to look at trips which are upcoming & unapproved."""
        # Unapproved, but it's in the past!
        self._make_climbing_trip(trip_date=date(2019, 7, 4))

        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)
        response = self.client.get("/climbing/trips/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["first_unapproved_trip"])

        # Make some future trips now - these trips will be ranked by date/itinerary!
        fri = self._make_climbing_trip(trip_date=date(2019, 7, 5))
        sun = self._make_climbing_trip(trip_date=date(2019, 7, 7))
        sat = self._make_climbing_trip(trip_date=date(2019, 7, 6))

        context = self.client.get("/climbing/trips/").context
        self.assertEqual(context["trips_needing_approval"], [fri, sat, sun])
        self.assertEqual(context["first_unapproved_trip"], fri)

    @freeze_time("2019-07-05 12:25:00 EST")
    def test_trips_with_itinerary_first(self):
        """Trips that have an itinerary are first in the approval flow."""
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        sat_with_info = self._make_climbing_trip(
            trip_date=date(2019, 7, 6),
            info=factories.TripInfoFactory.create(),
        )
        sat_without_info = self._make_climbing_trip(
            trip_date=date(2019, 7, 6), info=None
        )
        sun_with_info = self._make_climbing_trip(
            trip_date=date(2019, 7, 7),
            info=factories.TripInfoFactory.create(),
        )
        sun_without_info = self._make_climbing_trip(
            trip_date=date(2019, 7, 7), info=None
        )

        context = self.client.get("/climbing/trips/").context
        self.assertEqual(
            context["trips_needing_approval"],
            [sat_with_info, sat_without_info, sun_with_info, sun_without_info],
        )
        self.assertEqual(context["first_unapproved_trip"], sat_with_info)

    @freeze_time("2019-07-05 12:25:00 EST")
    def test_trips_needing_itinerary(self):
        perm_utils.make_chair(self.user, enums.Activity.CLIMBING)

        sat_trip = self._make_climbing_trip(trip_date=date(2019, 7, 6))
        sun_trip = self._make_climbing_trip(trip_date=date(2019, 7, 7))
        sun_trip_info = self._make_climbing_trip(
            trip_date=date(2019, 7, 7), info=factories.TripInfoFactory.create()
        )

        dean = factories.ParticipantFactory.create(
            name="Dean Potter", email="dean@example.com"
        )
        sun_trip.leaders.add(dean)

        # Leaders with multiple trips aren't repeated
        lynn = factories.ParticipantFactory.create(
            name="Lynn Hill", email="lynn@example.com"
        )
        sat_trip.leaders.add(lynn)
        sun_trip.leaders.add(lynn)

        # This trip is a week away; itineraries aren't open yet
        next_sat_trip = self._make_climbing_trip(trip_date=date(2019, 7, 13))

        # Alex has no trips that need itinerary
        alex = factories.ParticipantFactory.create(
            name="Alex Puccio", email="alex@example.com"
        )
        sun_trip_info.leaders.add(alex)
        next_sat_trip.leaders.add(alex)

        context = self.client.get("/climbing/trips/").context
        # Leaders are sorted by name
        self.assertEqual(
            context["leader_emails_missing_itinerary"],
            '"Dean Potter" <dean@example.com>, "Lynn Hill" <lynn@example.com>',
        )
