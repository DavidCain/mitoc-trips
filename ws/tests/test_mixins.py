from django.test import RequestFactory
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, mixins, models
from ws.tests import TestCase, factories


class MixedIn(mixins.LectureAttendanceMixin):
    """Dummy class that has a request!"""

    def __init__(self, request):
        self.request = request


class LectureAttendanceMixinTest(TestCase):
    @staticmethod
    def _can_set_attendance(request_par, target_participant):
        # Build a request that has a user & participant directly attached.
        request = RequestFactory().get('/')
        request.participant = request_par
        request.user = request_par.user

        mixed_in = MixedIn(request)
        return mixed_in.can_set_attendance(target_participant)

    @staticmethod
    def _allow_setting_attendance(allow=True):
        ws_settings = models.WinterSchoolSettings.load()
        ws_settings.allow_setting_attendance = allow
        ws_settings.save()

    @freeze_time("2019-01-10 12:25:00 EST")
    def test_can_set_self_during_iap(self):
        """So long as the setting is on, setting one's own attendance is allowed during IAP!."""
        par = factories.ParticipantFactory.create()

        self.assertFalse(self._can_set_attendance(par, par))  # (No settings found)

        self._allow_setting_attendance(False)
        self.assertFalse(self._can_set_attendance(par, par))

        self._allow_setting_attendance(True)
        self.assertTrue(self._can_set_attendance(par, par))

    @freeze_time("2019-08-15 12:25:00 EST")
    def test_cannot_set_outside_iap(self):
        """It must be during IAP in order to set attendance."""
        par = factories.ParticipantFactory.create()

        # Even if the setting is on, we deny due to time of year
        self._allow_setting_attendance()
        self.assertFalse(self._can_set_attendance(par, par))

    @freeze_time("2019-08-15 12:25:00 EST")
    def test_wsc_can_always_set(self):
        """Regardless of time of year, the WSC can always set attendance."""
        user = factories.UserFactory.create()
        perm_utils.make_chair(user, enums.Activity.WINTER_SCHOOL)
        par = factories.ParticipantFactory.create(user=user)

        other_par = factories.ParticipantFactory.create()
        self.assertTrue(self._can_set_attendance(par, other_par))

    @freeze_time("2019-08-15 12:25:00 EST")
    def test_admin_can_always_set(self):
        """Regardless of time of year, a superuser can always set attendance."""
        admin = factories.UserFactory.create(is_superuser=True)
        par = factories.ParticipantFactory.create(user=admin)

        other_par = factories.ParticipantFactory.create()
        self.assertTrue(self._can_set_attendance(par, other_par))
