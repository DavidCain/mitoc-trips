from bs4 import BeautifulSoup
from django.template import Context, Template
from django.test import TestCase
from freezegun import freeze_time

from ws.tests import factories, strip_whitespace


class AttendanceTest(TestCase):
    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_no_attendance_but_closed(self):
        participant = factories.ParticipantFactory.create()
        html_template = Template(
            "{% load ws_tags %}{% lecture_attendance par user_viewing %}"
        )
        context = Context({"par": participant, "user_viewing": True})
        soup = BeautifulSoup(html_template.render(context), "html.parser")

        # The user is marked as absent!
        self.assertTrue(soup.find(string="Absent", class_="label-danger"))

        # There's no option to submit attendance, just an instruction to email the chair(s)
        self.assertFalse(soup.find("form"))
        self.assertTrue(soup.find("a", href="mailto:ws-chair@mit.edu"))

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_no_attendance_and_signups_allowed(self):
        participant = factories.ParticipantFactory.create()
        html_template = Template(
            "{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}"
        )
        context = Context({"par": participant, "user_viewing": True, "can_set": True})
        soup = BeautifulSoup(html_template.render(context), "html.parser")

        self.assertTrue(
            soup.find(
                "p", string="We don't show you as having attended this year's lectures."
            )
        )
        self.assertTrue(
            soup.find("form", action="/winter_school/participants/lecture_attendance/")
        )
        submit_button = soup.find("button", {"type": "submit"})
        self.assertEqual(submit_button.text, "I attended lectures")

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_chair_viewing_other_participant(self):
        """Activity chairs can set attendance for other participants."""
        participant = factories.ParticipantFactory.create(name="Delinquent Participant")
        html_template = Template(
            "{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}"
        )
        context = Context({"par": participant, "user_viewing": False, "can_set": True})
        soup = BeautifulSoup(html_template.render(context), "html.parser")

        self.assertTrue(
            soup.find(
                "p",
                string="Delinquent Participant has not attended this year's lectures.",
            )
        )
        self.assertTrue(
            soup.find("form", action="/winter_school/participants/lecture_attendance/")
        )
        submit_button = soup.find("button", {"type": "submit"})
        self.assertEqual(submit_button.text, "Mark attendance")

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_leader_viewing_other_participant(self):
        """Leaders can view attendance for other participants."""
        participant = factories.ParticipantFactory.create(name="Delinquent Participant")
        html_template = Template(
            "{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}"
        )
        context = Context({"par": participant, "user_viewing": False, "can_set": False})
        soup = BeautifulSoup(html_template.render(context), "html.parser")

        self.assertTrue(soup.find(string="Absent", class_="label-danger"))
        self.assertEqual(
            soup.find("p").get_text(" ", strip=True),
            "Absent Delinquent Participant did not attend this year's lectures!",
        )
        self.assertFalse(soup.find("form"))
        self.assertFalse(soup.find("a", href="mailto:ws-chair@mit.edu"))

        # Past years' attendance can be shown, but only if existing
        self.assertNotIn("Past years' attendance", soup.text)
        factories.LectureAttendanceFactory.create(participant=participant, year=2015)
        factories.LectureAttendanceFactory.create(participant=participant, year=2017)
        factories.LectureAttendanceFactory.create(participant=participant, year=2018)

        soup = BeautifulSoup(html_template.render(context), "html.parser")
        self.assertIn("Past years' attendance", soup.text)
        self.assertEqual(
            [span.text for span in soup.find_all(class_="label-success")],
            ["2015", "2017", "2018"],
        )

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_leader_viewing_other_participant_has_attended(self):
        """Leaders can view attendance for other participants."""
        participant = factories.ParticipantFactory.create()
        factories.LectureAttendanceFactory.create(participant=participant, year=2019)
        html_template = Template(
            "{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}"
        )
        context = Context({"par": participant, "user_viewing": False, "can_set": False})
        soup = BeautifulSoup(html_template.render(context), "html.parser")

        self.assertTrue(soup.find(string="Attended", class_="label-success"))
        self.assertFalse(soup.find("form"))

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_self_has_attended(self):
        """We affirm that participants have attended lectures during the first week!"""
        participant = factories.ParticipantFactory.create()
        factories.LectureAttendanceFactory.create(participant=participant, year=2019)

        html_template = Template(
            "{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}"
        )
        base_context = {"par": participant, "user_viewing": True}

        html = html_template.render(Context({**base_context, "can_set": True}))
        paragraph = BeautifulSoup(html, "html.parser").find("p")
        self.assertEqual(
            strip_whitespace(paragraph.text),
            "Attended You have attended this year's lectures!",
        )

        # We tell the participant they've attended (whether or not the form is open)
        self.assertEqual(
            html_template.render(Context({**base_context, "can_set": False})),
            html_template.render(Context({**base_context, "can_set": True})),
        )

    @freeze_time("Jan 6 2022 20:00:00 EST")
    def test_self_missing_lecture_attendance(self):
        """We warn participants who are missing lecture attendance."""
        participant = factories.ParticipantFactory.create()
        html_template = Template(
            "{% load ws_tags %}{% lecture_attendance par user_viewing %}"
        )
        context = Context({"par": participant, "user_viewing": True})
        soup = BeautifulSoup(html_template.render(context), "html.parser")
        self.assertEqual(
            strip_whitespace(soup.find("p").text),
            "Absent You did not attend this year's lectures!",
        )
