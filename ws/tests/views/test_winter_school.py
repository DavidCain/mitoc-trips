from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, models
from ws.tests import TestCase, factories


# Test as if during WSC. Underlying mixin covers other edge cases.
@freeze_time("2019-01-10 12:25:00 EST")
class LectureAttendanceViewTest(TestCase):
    @staticmethod
    def _has_attended(participant, year, creator=None):
        attendance = models.LectureAttendance.objects.filter(
            participant=participant, year=year
        )
        if creator:
            attendance = attendance.filter(creator=creator)
        return attendance.exists()

    def _mark_attendance_for(self, participant, **kwargs):
        return self.client.post(
            '/winter_school/participants/lecture_attendance/',
            {'participant': participant.pk},
            **kwargs,
        )

    @staticmethod
    def _allow_setting_attendance(allow=True):
        ws_settings = models.WinterSchoolSettings.load()
        ws_settings.allow_setting_attendance = allow
        ws_settings.save()

    def test_redirects_home_on_get(self):
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)

        resp = self.client.get('/winter_school/participants/lecture_attendance/')
        self.assertEqual(resp.url, '/')
        self.assertEqual(resp.status_code, 302)

    def test_no_participant(self):
        """ Users who have no participant cannot mark attendance. """
        some_other_par = factories.ParticipantFactory.create()
        resp = self._mark_attendance_for(some_other_par)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(
            resp.url,
            '/accounts/login/?next=/winter_school/participants/lecture_attendance/',
        )

    def test_regular_participant_marking_another(self):
        """ Regular participants may not mark for others! """
        self._allow_setting_attendance()

        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)
        some_other_par = factories.ParticipantFactory.create()
        resp = self._mark_attendance_for(some_other_par)

        # The user won't have access to view other participants, but that's okay.
        # (They shouldn't have attempted this in the first place)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f'/participants/{some_other_par.pk}/')
        redir_resp = self.client.get(resp.url)
        self.assertEqual(redir_resp.status_code, 403)

    def test_cannot_mark_attendance(self):
        """ Participants may not be able to set their own attendance. """
        self._allow_setting_attendance(False)

        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)
        resp = self._mark_attendance_for(par)

        self.assertFalse(self._has_attended(par, 2019))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f'/participants/{par.pk}/')
        redir_resp = self.client.get(resp.url, follow=True)
        self.assertTrue(redir_resp.status_code, 200)

        messages = [obj.message for obj in redir_resp.context['messages']]
        self.assertIn("Unable to record your attendance at this time.", messages)

    def test_mark_attendance(self):
        """ Regular participants may mark their attendance if settings allow. """
        self._allow_setting_attendance()

        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)
        resp = self._mark_attendance_for(par)

        self.assertTrue(self._has_attended(par, 2019, creator=par))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f'/participants/{par.pk}/')
        redir_resp = self.client.get(resp.url, follow=True)
        self.assertTrue(redir_resp.status_code, 200)

        messages = [obj.message for obj in redir_resp.context['messages']]
        self.assertIn("Marked as having attended lectures!", messages)

    def test_wsc_can_mark_attendance(self):
        """ The WSC can mark other participants as having attended. """
        wsc_member = factories.ParticipantFactory.create()
        perm_utils.make_chair(wsc_member.user, enums.Activity.WINTER_SCHOOL)
        self.client.force_login(wsc_member.user)

        self._allow_setting_attendance()

        other_par = factories.ParticipantFactory.create()
        resp = self._mark_attendance_for(other_par)

        self.assertTrue(self._has_attended(other_par, 2019, creator=wsc_member))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, f'/participants/{other_par.pk}/')
        redir_resp = self.client.get(resp.url, follow=True)
        self.assertTrue(redir_resp.status_code, 200)

        messages = [obj.message for obj in redir_resp.context['messages']]
        self.assertNotIn("Marked as having attended lectures!", messages)


class WinterSchoolSettingsTest(TestCase):
    def _load_as_wsc(self):
        wsc_member = factories.ParticipantFactory.create()
        perm_utils.make_chair(wsc_member.user, enums.Activity.WINTER_SCHOOL)
        self.client.force_login(wsc_member.user)

        return self.client.get('/winter_school/settings/')

    def test_not_wsc(self):
        """ Only the WSC can view/modify. """
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)
        resp = self.client.get('/winter_school/settings/')
        self.assertEqual(resp.status_code, 403)

    def test_no_settings_to_start(self):
        """ We can load even without the singleton being in the database. """
        with self.assertRaises(models.WinterSchoolSettings.DoesNotExist):
            models.WinterSchoolSettings.objects.get()

        self._load_as_wsc()
        settings = models.WinterSchoolSettings.objects.get()
        self.assertFalse(settings.allow_setting_attendance)
        self.assertTrue(settings.accept_applications)

    def test_change_settings(self):
        """ The Winter Safety Committee can change Winter School settings. """
        self._load_as_wsc()

        # We started false!
        settings = models.WinterSchoolSettings.objects.get()
        self.assertFalse(settings.allow_setting_attendance)

        resp = self.client.post(
            '/winter_school/settings/', {'allow_setting_attendance': True}
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, '/winter_school/settings/')

        # Now, setting attendance is allowed!
        settings.refresh_from_db()
        self.assertTrue(settings.allow_setting_attendance)
