from datetime import date, datetime
from unittest import mock

import pytz
from bs4 import BeautifulSoup
from django.contrib.auth.models import Group
from freezegun import freeze_time

import ws.utils.perms as perm_utils
from ws import enums, models, tasks
from ws.tests import TestCase, factories


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
        Group.objects.get(name='WIMP').user_set.add(wimp_par.user_id)
        return wimp_par

    def test_admins_always_see_wimp(self):
        admin = factories.UserFactory.create(is_superuser=True)
        factories.ParticipantFactory.create(user_id=admin.pk)
        self.client.force_login(admin)
        wimp_par = self._create_wimp()

        resp = self.client.get('/')
        self.assertEqual(resp.context['wimp'], wimp_par)

    def test_participants_not_shown_wimp(self):
        # Upcoming WS trip exists
        factories.TripFactory.create(
            trip_date=date(2020, 1, 20), program=enums.Program.WINTER_SCHOOL.value
        )
        self._create_wimp()

        # Normal participants don't see the WIMP
        resp = self.client.get('/')
        self.assertIsNone(resp.context['wimp'])

    def test_no_wimp_shown_until_upcoming_ws_trips(self):
        # Trip exists from yesterday (it's currently during IAP too)
        factories.TripFactory.create(
            trip_date=date(2020, 1, 11), program=enums.Program.WINTER_SCHOOL.value
        )

        # Viewing participant is a WS leader
        factories.LeaderRatingFactory.create(
            participant=self.participant, activity=enums.Activity.WINTER_SCHOOL.value,
        )

        # We have an assigned WIMP
        wimp_par = self._create_wimp()

        # Because there are no upcoming WS trips, though - no WIMP is shown
        resp = self.client.get('/')
        self.assertIsNone(resp.context['wimp'])

        # If a trip is created today, we will then show the WIMP!
        factories.TripFactory.create(
            trip_date=date(2020, 1, 12), program=enums.Program.WINTER_SCHOOL.value
        )

        # Now, we show the WIMP because there are upcoming WS trips
        resp = self.client.get('/')
        self.assertEqual(resp.context['wimp'], wimp_par)

    def test_chairs_see_wimp_even_if_not_leaders(self):
        # WS trip exists today!
        factories.TripFactory.create(
            trip_date=date(2020, 1, 12), program=enums.Program.WINTER_SCHOOL.value
        )
        perm_utils.make_chair(self.user, enums.Activity.WINTER_SCHOOL)
        wimp_par = self._create_wimp()

        # There are upcoming WS trips, so the WS chairs should see the WIMP
        resp = self.client.get('/')
        self.assertEqual(resp.context['wimp'], wimp_par)


@freeze_time("2019-02-15 12:25:00 EST")
class EditProfileViewTests(TestCase):
    # 3 separate forms (does not include a car!)
    form_data = {
        # Participant
        'participant.name': 'New Participant',
        'participant.email': 'new.participant@example.com',
        'participant.cell_phone': '+1 800-555-0000',
        'participant.affiliation': 'NA',
        # Emergency information
        'einfo.allergies': 'N/A',
        'einfo.medications': 'N/A',
        'einfo.medical_history': 'Nothing relevant',
        # Emergency contact
        'econtact.name': 'Participant Sister',
        'econtact.email': 'sister@example.com',
        'econtact.cell_phone': '+1 800-555-1234',
        'econtact.relationship': 'Sister',
    }

    def setUp(self):
        super().setUp()
        self.user = factories.UserFactory.create()
        self.client.force_login(self.user)

    def _assert_form_data_saved(self, participant):
        """ Assert that the given participant has data from `form_data`. """
        self.assertEqual(participant.name, 'New Participant')
        self.assertEqual(participant.email, 'new.participant@example.com')
        self.assertEqual(participant.affiliation, 'NA')
        self.assertEqual(participant.cell_phone.as_e164, '+18005550000')

        self.assertIsNone(participant.car)

        e_contact = participant.emergency_info.emergency_contact
        expected_contact = models.EmergencyContact(
            pk=e_contact.pk,
            name='Participant Sister',
            email='sister@example.com',
            cell_phone=mock.ANY,  # Tested below
            relationship='Sister',
        )

        self.assertEqual(
            participant.emergency_info,
            models.EmergencyInfo(
                pk=participant.emergency_info.pk,
                allergies='N/A',
                medications='N/A',
                medical_history='N/A',
                emergency_contact=expected_contact,
            ),
        )
        self.assertEqual(e_contact.cell_phone.as_e164, '+18005551234')

    def test_new_participant(self):
        response = self.client.get('/profile/edit/')
        soup = BeautifulSoup(response.content, 'html.parser')

        self.assertEqual(
            soup.find(class_='alert').get_text(strip=True),
            'Please complete this important safety information to finish the signup process.',
        )
        with mock.patch.object(tasks, 'update_participant_affiliation') as task_update:
            response = self.client.post('/profile/edit/', self.form_data, follow=False)

        # The save was successful, redirects home
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

        participant = models.Participant.objects.get(
            email='new.participant@example.com'
        )

        self._assert_form_data_saved(participant)

        # We call an async task to update the affiliation for the participant
        task_update.delay.assert_called_with(participant.pk)

        # We then update the timestamps!
        now = datetime(2019, 2, 15, 17, 25, tzinfo=pytz.utc)
        self.assertEqual(participant.last_updated, now)
        # Since the participant modified their own profile, we save `profile_last_updated`
        self.assertEqual(participant.profile_last_updated, now)

    def test_existing_participant_with_problems(self):
        factories.ParticipantFactory.create(name='Cher', user_id=self.user.pk)

        response = self.client.get('/profile/edit/')
        soup = BeautifulSoup(response.content, 'html.parser')

        self.assertEqual(
            soup.find(class_='alert').get_text(strip=True),
            "Please supply your full legal name.",
        )
