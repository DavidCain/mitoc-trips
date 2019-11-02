from bs4 import BeautifulSoup
from django.template import Context, Template
from freezegun import freeze_time

from ws.tests import TestCase, factories


class AttendanceTest(TestCase):
    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_no_attendance_but_closed(self):
        participant = factories.ParticipantFactory.create()
        html_template = Template(
            '{% load ws_tags %}{% lecture_attendance par user_viewing %}'
        )
        context = Context({'par': participant, 'user_viewing': True})
        soup = BeautifulSoup(html_template.render(context), 'html.parser')

        # The user is marked as absent!
        self.assertTrue(soup.find(text='Absent', class_='label-danger'))

        # There's no option to submit attendance, just an instruction to email the chair(s)
        self.assertFalse(soup.find('form'))
        self.assertTrue(soup.find('a', href="mailto:ws-chair@mit.edu"))

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_no_attendance_and_signups_allowed(self):
        participant = factories.ParticipantFactory.create()
        html_template = Template(
            '{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}'
        )
        context = Context({'par': participant, 'user_viewing': True, 'can_set': True})
        soup = BeautifulSoup(html_template.render(context), 'html.parser')

        self.assertTrue(
            soup.find(
                'p', text="We don't show you as having attended this year's lectures."
            )
        )
        self.assertTrue(
            soup.find('form', action='/winter_school/participants/lecture_attendance/')
        )
        submit_button = soup.find('button', {'type': 'submit'})
        self.assertEqual(submit_button.text, 'I attended lectures')

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_chair_viewing_other_participant(self):
        """ Activity chairs can set attendance for other participants. """
        participant = factories.ParticipantFactory.create(name='Delinquent Participant')
        html_template = Template(
            '{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}'
        )
        context = Context({'par': participant, 'user_viewing': False, 'can_set': True})
        soup = BeautifulSoup(html_template.render(context), 'html.parser')

        self.assertTrue(
            soup.find(
                'p',
                text="Delinquent Participant has not attended this year's lectures.",
            )
        )
        self.assertTrue(
            soup.find('form', action='/winter_school/participants/lecture_attendance/')
        )
        submit_button = soup.find('button', {'type': 'submit'})
        self.assertEqual(submit_button.text, 'Mark attendance')

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_leader_viewing_other_participant(self):
        """ Leaders can view attendance for other participants. """
        participant = factories.ParticipantFactory.create(name='Delinquent Participant')
        html_template = Template(
            '{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}'
        )
        context = Context({'par': participant, 'user_viewing': False, 'can_set': False})
        soup = BeautifulSoup(html_template.render(context), 'html.parser')

        self.assertTrue(soup.find(text='Absent', class_='label-danger'))
        self.assertEqual(
            soup.find('p').get_text(' ', strip=True),
            "Absent Delinquent Participant did not attend this year's lectures!",
        )
        self.assertFalse(soup.find('form'))
        self.assertFalse(soup.find('a', href="mailto:ws-chair@mit.edu"))

        # Past years' attendance can be shown, but only if existing
        self.assertNotIn("Past years' attendance", soup.text)
        factories.LectureAttendanceFactory.create(participant=participant, year=2015)
        factories.LectureAttendanceFactory.create(participant=participant, year=2017)
        factories.LectureAttendanceFactory.create(participant=participant, year=2018)

        soup = BeautifulSoup(html_template.render(context), 'html.parser')
        self.assertIn("Past years' attendance", soup.text)
        self.assertEqual(
            [span.text for span in soup.find_all(class_='label-success')],
            ['2015', '2017', '2018'],
        )

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_leader_viewing_other_participant_has_attended(self):
        """ Leaders can view attendance for other participants. """
        participant = factories.ParticipantFactory.create()
        factories.LectureAttendanceFactory.create(participant=participant, year=2019)
        html_template = Template(
            '{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}'
        )
        context = Context({'par': participant, 'user_viewing': False, 'can_set': False})
        soup = BeautifulSoup(html_template.render(context), 'html.parser')

        self.assertTrue(soup.find(text='Attended', class_='label-success'))
        self.assertFalse(soup.find('form'))

    @freeze_time("Jan 12 2019 20:30:00 EST")
    def test_self_has_attended(self):
        """ We show nothing when participants have signed in and it's WS. """
        participant = factories.ParticipantFactory.create()
        factories.LectureAttendanceFactory.create(participant=participant, year=2019)
        html_template = Template(
            '{% load ws_tags %}{% lecture_attendance par user_viewing can_set %}'
        )

        # Does not matter if able to set or not - we have nothing to display
        self.assertFalse(
            html_template.render(
                Context({'par': participant, 'user_viewing': True, 'can_set': True})
            ).strip()
        )
        self.assertFalse(
            html_template.render(
                Context({'par': participant, 'user_viewing': True, 'can_set': False})
            ).strip()
        )
