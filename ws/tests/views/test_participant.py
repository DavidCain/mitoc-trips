from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from django.contrib.auth.models import Group
from django.test import TestCase
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, models, tasks
from ws.templatetags import general_tags
from ws.tests import factories, strip_whitespace
from ws.views.participant import logger


class LandingPageTests(TestCase):
    @freeze_time("2020-01-12 09:00:00 EST")
    def test_unauthenticated_rendering_enough_upcoming_trips(self):
        # Ten upcoming trips, with the next-upcoming trips first
        ten_upcoming_trips = [
            factories.TripFactory.create(trip_date=date(2020, 2, 1 + i))
            for i in range(10)
        ]

        response = self.client.get("/")
        soup = BeautifulSoup(response.content, "html.parser")
        lead_paragraph = soup.find("p", class_="lead")
        self.assertEqual(
            lead_paragraph.text,
            "Come hiking, climbing, skiing, paddling, biking, and surfing with the MIT Outing Club!",
        )

        # All trips are listed in chronological order
        self.assertEqual(list(response.context["current_trips"]), ten_upcoming_trips)
        # No recent trips are needed, since we have more than eight
        self.assertNotIn("recent_trips", response.context)

    @freeze_time("2020-01-12 09:00:00 EST")
    def test_unauthenticated_rendering_few_upcoming_trips(self):
        # Ten previous trips, with the most recent ones first
        ten_past_trips = [
            factories.TripFactory.create(trip_date=date(2019, 12, 30 - i))
            for i in range(1, 11)
        ]

        upcoming_trip1 = factories.TripFactory.create(trip_date=date(2020, 1, 15))
        upcoming_trip2 = factories.TripFactory.create(trip_date=date(2020, 1, 20))

        response = self.client.get("/")

        # Upcoming trips are listed in chronological order
        self.assertEqual(
            list(response.context["current_trips"]), [upcoming_trip1, upcoming_trip2]
        )
        # Recent trips are shown until we have 8 total
        self.assertEqual(list(response.context["recent_trips"]), ten_past_trips[:6])

        soup = BeautifulSoup(response.content, "html.parser")
        prev_trips = soup.find("a", href="/trips/?after=2019-01-12")
        self.assertEqual(prev_trips.get_text(strip=True), "Previous trips")


# NOTE: See test_ws_tags.py for direct testing of the templatetag too
class LectureAttendanceTests(TestCase):
    def setUp(self):
        super().setUp()
        self.participant = factories.ParticipantFactory.create()
        self.client.force_login(self.participant.user)

    @staticmethod
    def _allow_setting_attendance(allow=True):
        ws_settings = models.WinterSchoolSettings.load()
        ws_settings.allow_setting_attendance = allow
        ws_settings.save()

    def test_success_is_shown_in_week_one(self):
        """We show participants that yes, they did in fact attend lectures.

        Participants have been confused if they submitted their attendance, then
        refreshed the page and saw no indicator that their attendance was recorded.
        """
        self._allow_setting_attendance()
        factories.LectureAttendanceFactory.create(
            participant=self.participant, year=2022
        )

        with freeze_time("Jan 6 2022 20:00:00 EST"):
            resp = self.client.get("/")
        soup = BeautifulSoup(resp.content, "html.parser")
        attendance = soup.find("h3", string="Lecture Attendance")
        self.assertEqual(
            strip_whitespace(attendance.find_next("p").text),
            "Attended You have attended WS 2022 lectures!",
        )

    def test_warn_if_missing_after_lectures(self):
        """If lectures have ended, we warn participants without attendance."""
        factories.LectureAttendanceFactory.create(
            participant=self.participant, year=2022
        )
        # Participants cannot set attendance; that time has passed.
        self._allow_setting_attendance(False)

        # A future WS trip exists, which is a strong clue: it must be first week of WS
        with freeze_time("2022-01-04 12:00:00 EST"):
            factories.TripFactory.create(
                trip_date=date(2022, 1, 8),
                program=enums.Program.WINTER_SCHOOL.value,
            )

        # It's after 9 pm on Thursday (with future WS trips). Must be lecture day.
        with freeze_time("2022-01-06 22:00:00 EST"):
            resp = self.client.get("/")

        # This participant did not record their attendance!
        soup = BeautifulSoup(resp.content, "html.parser")
        attendance = soup.find("h3", string="Lecture Attendance")
        self.assertEqual(
            strip_whitespace(attendance.find_next("p").text),
            "Attended You have attended WS 2022 lectures!",
        )

    def test_attendance_not_shown_in_week_two(self):
        """We don't tell participants that they attended lectures after the first week."""
        factories.LectureAttendanceFactory.create(
            participant=self.participant, year=2022
        )

        # We created a trip for Saturday in the first weekend
        with freeze_time("2022-01-04 12:00:00 EST"):
            factories.TripFactory.create(
                trip_date=date(2022, 1, 8),
                program=enums.Program.WINTER_SCHOOL.value,
            )

        # It's Monday *after* the first week's trips.
        # It's possible that no new future trips exist.
        with freeze_time("2022-01-10 22:00:00 EST"):
            resp = self.client.get("/")

        # Because the participant *did* attend lectures, we don't take up space telling them that
        soup = BeautifulSoup(resp.content, "html.parser")
        self.assertFalse(soup.find("h3", string="Lecture Attendance"))

    def test_attendance_not_shown_outside_winter_school(self):
        """We don't tell participants that they attended lectures, outside WS at least."""
        factories.LectureAttendanceFactory.create(
            participant=self.participant, year=2022
        )
        # We even account for the possibility that WS chairs left the setting on.
        self._allow_setting_attendance()

        with freeze_time("Feb 15 2022 12:00:00 EST"):
            resp = self.client.get("/")
        soup = BeautifulSoup(resp.content, "html.parser")
        self.assertFalse(soup.find("h3", string="Lecture Attendance"))


class ProfileViewTests(TestCase):
    def test_dated_affiliation_redirect(self):
        # Make a participant with a legacy affiliation
        participant = factories.ParticipantFactory.create(affiliation="S")
        self.client.force_login(participant.user)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, "/profile/edit/")


@freeze_time("2020-01-12 09:00:00 EST")
class WimpDisplayInProfileViewTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = factories.UserFactory.create()
        self.participant = factories.ParticipantFactory.create(user_id=self.user.pk)
        self.client.force_login(self.user)

    @staticmethod
    def _create_wimp():
        wimp_par = factories.ParticipantFactory.create()
        Group.objects.get(name="WIMP").user_set.add(wimp_par.user_id)
        return wimp_par

    def test_admins_always_see_wimp(self):
        admin = factories.UserFactory.create(is_superuser=True)
        factories.ParticipantFactory.create(user_id=admin.pk)
        self.client.force_login(admin)
        wimp_par = self._create_wimp()

        resp = self.client.get("/")
        self.assertEqual(resp.context["wimp"], wimp_par)

    def test_participants_not_shown_wimp(self):
        # Upcoming WS trip exists
        factories.TripFactory.create(
            trip_date=date(2020, 1, 20), program=enums.Program.WINTER_SCHOOL.value
        )
        self._create_wimp()

        # Normal participants don't see the WIMP
        resp = self.client.get("/")
        self.assertIsNone(resp.context["wimp"])

    def test_no_wimp_shown_until_upcoming_ws_trips(self):
        # Trip exists from yesterday (it's currently during IAP too)
        factories.TripFactory.create(
            trip_date=date(2020, 1, 11), program=enums.Program.WINTER_SCHOOL.value
        )

        # Viewing participant is a WS leader
        factories.LeaderRatingFactory.create(
            participant=self.participant,
            activity=enums.Activity.WINTER_SCHOOL.value,
        )

        # We have an assigned WIMP
        wimp_par = self._create_wimp()

        # Because there are no upcoming WS trips, though - no WIMP is shown
        resp = self.client.get("/")
        self.assertIsNone(resp.context["wimp"])

        # If a trip is created today, we will then show the WIMP!
        factories.TripFactory.create(
            trip_date=date(2020, 1, 12), program=enums.Program.WINTER_SCHOOL.value
        )

        # Now, we show the WIMP because there are upcoming WS trips
        resp = self.client.get("/")
        self.assertEqual(resp.context["wimp"], wimp_par)

    def test_chairs_see_wimp_even_if_not_leaders(self):
        # WS trip exists today!
        factories.TripFactory.create(
            trip_date=date(2020, 1, 12), program=enums.Program.WINTER_SCHOOL.value
        )
        perm_utils.make_chair(self.user, enums.Activity.WINTER_SCHOOL)
        wimp_par = self._create_wimp()

        # There are upcoming WS trips, so the WS chairs should see the WIMP
        resp = self.client.get("/")
        self.assertEqual(resp.context["wimp"], wimp_par)


@freeze_time("2019-02-15 12:25:00 EST")
class EditProfileViewTests(TestCase):
    # 3 separate forms (does not include a car!)
    form_data = {
        # Participant
        "participant-name": "New Participant",
        "participant-email": "new.participant@example.com",
        "participant-cell_phone": "+1 800-555-0000",
        "participant-affiliation": "NA",
        # Emergency information
        "einfo-allergies": "N/A",
        "einfo-medications": "N/A",
        "einfo-medical_history": "Nothing relevant",
        # Emergency contact
        "econtact-name": "Participant Sister",
        "econtact-email": "sister@example.com",
        "econtact-cell_phone": "+1 800-555-1234",
        "econtact-relationship": "Sister",
    }

    def setUp(self):
        super().setUp()
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def _assert_form_data_saved(self, participant):
        """Assert that the given participant has data from `form_data`."""
        self.assertEqual(participant.name, "New Participant")
        self.assertEqual(participant.email, "new.participant@example.com")
        self.assertEqual(participant.affiliation, "NA")
        self.assertEqual(participant.cell_phone.as_e164, "+18005550000")

        self.assertIsNone(participant.car)

        e_contact = participant.emergency_info.emergency_contact
        expected_contact = models.EmergencyContact(
            pk=e_contact.pk,
            name="Participant Sister",
            email="sister@example.com",
            cell_phone=mock.ANY,  # Tested below
            relationship="Sister",
        )

        self.assertEqual(
            participant.emergency_info,
            models.EmergencyInfo(
                pk=participant.emergency_info.pk,
                allergies="N/A",
                medications="N/A",
                medical_history="N/A",
                emergency_contact=expected_contact,
            ),
        )
        self.assertEqual(e_contact.cell_phone.as_e164, "+18005551234")

    def test_new_participant(self):
        response = self.client.get("/profile/edit/")
        soup = BeautifulSoup(response.content, "html.parser")

        self.assertEqual(
            soup.find(class_="alert").get_text(strip=True),
            "Please complete this important safety information to finish the signup process.",
        )
        with mock.patch.object(tasks, "update_participant_affiliation") as task_update:
            response = self.client.post("/profile/edit/", self.form_data, follow=False)

        # The save was successful, redirects home
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

        participant = models.Participant.objects.get(
            email="new.participant@example.com"
        )

        self._assert_form_data_saved(participant)

        # We call an async task to update the affiliation for the participant
        task_update.delay.assert_called_with(participant.pk)

        # We then update the timestamps!
        now = datetime(2019, 2, 15, 17, 25, tzinfo=ZoneInfo("UTC"))
        self.assertEqual(participant.last_updated, now)
        # Since the participant modified their own profile, we save `profile_last_updated`
        self.assertEqual(participant.profile_last_updated, now)

    def test_existing_participant_with_problems(self):
        factories.ParticipantFactory.create(name="Cher", user_id=self.user.pk)

        response = self.client.get("/profile/edit/")
        soup = BeautifulSoup(response.content, "html.parser")

        self.assertEqual(
            soup.find(class_="alert").get_text(strip=True),
            "Please supply your full legal name.",
        )


class ParticipantDetailViewTest(TestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

        self.participant = factories.ParticipantFactory.create()

    def test_non_authenticated_redirected(self):
        self.client.logout()
        response = self.client.get(f"/participants/{self.participant.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, f"/accounts/login/?next=/participants/{self.participant.pk}/"
        )

    def test_non_participants_redirected(self):
        user = factories.UserFactory.create()
        self.client.force_login(user)
        response = self.client.get(f"/participants/{self.participant.pk}/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, f"/profile/edit/?next=/participants/{self.participant.pk}/"
        )

    def test_non_leaders_blocked(self):
        factories.ParticipantFactory.create(user_id=self.user.pk)
        response = self.client.get(f"/participants/{self.participant.pk}/")

        self.assertEqual(response.status_code, 403)

    def test_redirect_to_own_home(self):
        par = factories.ParticipantFactory.create(user_id=self.user.pk)
        response = self.client.get(f"/participants/{par.pk}/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_leaders_can_view_others(self):
        par = factories.ParticipantFactory.create(user_id=self.user.pk)

        factories.FeedbackFactory.create(participant=self.participant)
        factories.FeedbackFactory.create(
            participant=self.participant,
            showed_up=False,
            comments="Slept through their alarm, did not answer phone calls",
        )

        # Any leader may view - it doesn't matter which activity!
        factories.LeaderRatingFactory.create(participant=par)
        self.assertTrue(perm_utils.is_leader(self.user))
        general_tags.SCRAMBLER.seed("Set seed, for predictable 'scrambling'")
        response = self.client.get(f"/participants/{self.participant.pk}/")
        self.assertEqual(response.status_code, 200)

        # When viewing, comments are initially scrambled
        soup = BeautifulSoup(response.content, "html.parser")
        feedback = soup.find(id="feedback").find_next("table")
        self.assertEqual(
            strip_whitespace(feedback.find_next("td").text),
            # 'Slept through their alarm, did not answer phone calls'
            "ursde itdhate toeah ailgnS wos rlt plamlh ropcr neh,n",
        )

        # There's a button which enables us to view this feedback, unscrambled.
        reveal = soup.find(
            "a", href=f"/participants/{self.participant.pk}/?show_feedback=1"
        )
        self.assertEqual(
            strip_whitespace(reveal.text),
            "Show feedback for trip-planning purposes",
        )
        with mock.patch.object(logger, "info") as log_info:
            response = self.client.get(reveal.attrs["href"])
        log_info.assert_called_once_with(
            "%s (#%d) viewed feedback for %s (#%d)",
            par,
            par.pk,
            self.participant,
            self.participant.pk,
        )
        soup = BeautifulSoup(response.content, "html.parser")
        feedback = soup.find(id="feedback").find_next("table")
        self.assertEqual(
            strip_whitespace(feedback.find_next("td").text),
            "Flaked! Slept through their alarm, did not answer phone calls",
        )

    def test_only_old_feedback(self):
        """We convey if a participant has *only* old feedback on record."""
        # Make the viewer a leader so they can view feedback
        par = factories.ParticipantFactory.create(user_id=self.user.pk)
        factories.LeaderRatingFactory.create(participant=par)

        # Simulate some old feedback!
        with freeze_time("2022-12-26 12:00 UTC"):
            factories.FeedbackFactory.create(
                participant=self.participant,
                showed_up=False,
                comments="Slept through their alarm, did not answer phone calls",
            )
        with freeze_time("2024-01-28T12:00-05:00"):
            response = self.client.get(f"/participants/{self.participant.pk}/")
        soup = BeautifulSoup(response.content, "html.parser")

        # There's nothing to alert the leader about -- no feedback is *expected*
        # We'll instead just surface this information in a plain `<p>`
        self.assertIsNone(soup.find(class_="alert"))

        old_feedback_msg = (
            "This participant was given feedback before Dec. 29, 2022. "
            "Per club policy, we hide all feedback after thirteen months. "
            "If you need to see old feedback, reach out to the appropriate activity chair(s)."
        )
        self.assertEqual(
            strip_whitespace(soup.find("p", id="has-old-feedback").text),
            old_feedback_msg,
        )

        # We handle "show_feedback" even though there won't be a button for it.
        self.assertIsNone(
            soup.find("button", string="Show feedback for trip-planning purposes")
        )
        with freeze_time("2024-01-28T12:00-05:00"):
            response2 = self.client.get(
                f"/participants/{self.participant.pk}/?show_feedback=1"
            )
        soup2 = BeautifulSoup(response2.content, "html.parser")
        # We won't warn about "access logged" since there's nothing to show
        self.assertIsNone(soup2.find("span", class_="label-info"))
        self.assertEqual(
            strip_whitespace(soup.find("p", id="has-old-feedback").text),
            old_feedback_msg,
        )

    def test_bygone_feedback(self):
        """Feedback older than 13 months is automatically hidden!"""
        # Make the viewer a leader so they can view feedback
        par = factories.ParticipantFactory.create(user_id=self.user.pk)
        factories.LeaderRatingFactory.create(participant=par)

        # Simulate some old feedback!
        with freeze_time("2022-12-26 12:00 UTC"):
            factories.FeedbackFactory.create(
                participant=self.participant,
                showed_up=False,
                comments="Slept through their alarm, did not answer phone calls",
            )
        with freeze_time("2024-01-28T12:00-05:00"):
            factories.FeedbackFactory.create(
                participant=self.participant,
                comments="Right on time! Figured out their alarm.",
            )

            default_response = self.client.get(f"/participants/{self.participant.pk}/")
            show_feedback_response = self.client.get(
                f"/participants/{self.participant.pk}/?show_feedback=1"
            )

        default_soup = BeautifulSoup(default_response.content, "html.parser")
        # Until they click "Show feedback for trip-planning purposes," we don't reveal old feedback
        # (there's no point in warning about old feedback when *current* feedback is obscured)
        self.assertIsNone(default_soup.find(class_="alert"))

        soup = BeautifulSoup(show_feedback_response.content, "html.parser")
        self.assertEqual(
            soup.find("span", class_="label-info").text,
            "Your access has been logged.",
        )

        self.assertEqual(
            strip_whitespace(soup.find(class_="alert").text),
            (
                "This participant was also given feedback before Dec. 29, 2022. "
                "Per club policy, we hide all feedback after thirteen months. "
                "If you truly need to see old feedback, please reach out to the appropriate activity chair(s)."
            ),
        )

        feedback = soup.find(id="feedback").find_next("table")
        self.assertIn("Right on time!", feedback.text)
        self.assertNotIn("Slept through their alarm", feedback.text)
