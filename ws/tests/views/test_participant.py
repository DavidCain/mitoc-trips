from datetime import datetime
from unittest import mock

import pytz
from bs4 import BeautifulSoup
from freezegun import freeze_time

from ws import models, tasks
from ws.tests import TestCase, factories


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
