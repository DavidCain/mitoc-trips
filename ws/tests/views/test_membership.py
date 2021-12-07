from datetime import date
from unittest import mock

from bs4 import BeautifulSoup
from freezegun import freeze_time

from ws import forms, waivers
from ws.tests import TestCase, factories, strip_whitespace


class PayDuesTests(TestCase):
    def test_load_form_as_anonymous_user(self):
        """Several hidden inputs are pre-filled for all members."""
        response = self.client.get('/profile/membership/')
        form = response.context['form']

        self.assertEqual(form.fields['merchant_id'].initial, 'mit_sao_mitoc')
        self.assertEqual(form.fields['description'].initial, 'membership fees.')

        # merchant* fields have special meaning for CyberSource.
        # - The `'membership'` label is expected in mitoc-member
        # The Affiliation is also used to create the membership record
        self.assertEqual(form.fields['merchantDefinedData1'].initial, 'membership')
        self.assertEqual(
            form.fields['merchantDefinedData2'].choices,
            [
                (
                    'Undergraduate student',
                    [('MU', 'MIT undergrad ($15)'), ('NU', 'Non-MIT undergrad ($40)')],
                ),
                (
                    'Graduate student',
                    [
                        ('MG', 'MIT grad student ($15)'),
                        ('NG', 'Non-MIT grad student ($40)'),
                    ],
                ),
                (
                    'MIT',
                    [
                        ('MA', 'MIT affiliate (staff or faculty) ($30)'),
                        ('ML', 'MIT alum (former student) ($40)'),
                    ],
                ),
                ('NA', 'Non-affiliate ($40)'),
            ],
        )

        # The user must self report their email address and select an affiliation
        self.assertEqual(form.fields['amount'].initial, '')
        self.assertIsNone(form.fields['merchantDefinedData3'].initial)

    def test_load_form_as_logged_in_participant(self):
        """We pre-populate the form for participants with information on file."""
        par = factories.ParticipantFactory.create(
            user=factories.UserFactory.create(email='tim@mit.edu'), affiliation='MA'
        )
        self.client.force_login(par.user)
        response = self.client.get('/profile/membership/')
        self.assertEqual(response.status_code, 200)
        form = response.context['form']

        self.assertEqual(form.fields['merchant_id'].initial, 'mit_sao_mitoc')
        self.assertEqual(form.fields['description'].initial, 'membership fees.')
        self.assertEqual(form.fields['amount'].initial, 30)  # Annual affiliate dues
        self.assertEqual(form.fields['merchantDefinedData1'].initial, 'membership')
        self.assertEqual(form.fields['merchantDefinedData2'].initial, 'MA')
        self.assertEqual(form.fields['merchantDefinedData3'].initial, 'tim@mit.edu')

    @freeze_time("2021-12-10 12:00:00 EST")
    def test_load_form_as_member_able_to_renew(self):
        """We clearly communicate when membership ends if you renew."""
        par = factories.ParticipantFactory.create(
            membership__membership_expires=date(2021, 12, 25)
        )
        self.assertTrue(par.membership.in_early_renewal_period)
        self.client.force_login(par.user)

        response = self.client.get('/profile/membership/')

        soup = BeautifulSoup(response.content, 'html.parser')
        lead_par = soup.find('p', class_='lead')
        self.assertEqual(
            lead_par.text, 'To make the most of MITOC, you must be an active member.'
        )
        self.assertEqual(
            strip_whitespace(lead_par.find_next('p').text),
            'Renewing today keeps your membership active until Dec 25, 2022. '
            "Membership enables you to rent gear from the office, participate in upcoming trips, and stay at MITOC's cabins.",
        )

    @freeze_time("2021-12-10 12:00:00 EST")
    def test_load_form_as_lapsed_member(self):
        par = factories.ParticipantFactory.create(
            membership__membership_expires=date(2021, 1, 2)
        )
        self.assertFalse(par.membership.in_early_renewal_period)
        self.assertEqual(par.membership.expiry_if_paid_today, date(2022, 12, 10))

        self.client.force_login(par.user)

        response = self.client.get('/profile/membership/')

        soup = BeautifulSoup(response.content, 'html.parser')
        lead_par = soup.find('p', class_='lead')
        self.assertEqual(
            lead_par.text, 'To make the most of MITOC, you must be an active member.'
        )
        self.assertEqual(
            strip_whitespace(lead_par.find_next('p').text),
            "Membership lasts for 365 days after dues are paid, and enables you to "
            "rent gear from the office, participate in upcoming trips, and stay at MITOC's cabins.",
        )

    def test_pay_anonymously(self):
        """Users need not log in to pay dues."""
        valid_form_data = {
            'merchant_id': 'mit_sao_mitoc',
            'description': 'membership fees.',
            'merchantDefinedData1': 'membership',
            'merchantDefinedData2': 'NA',
            'merchantDefinedData3': 'tim@mit.edu',
            'amount': 40,
        }

        # If this were a normal form view, the values above would be accepted
        self.assertTrue(forms.DuesForm(valid_form_data, participant=None).is_valid())

        # However, submitting directly is not allowed
        response = self.client.post('/profile/membership/', valid_form_data)
        self.assertEqual(response.status_code, 405)

        # We can't test that CyberSource accepts the payload, so stop here


class SignWaiverTests(TestCase):
    def test_sign_as_anonymous_user(self):
        """You don't need to be logged in to sign a waiver."""
        response = self.client.get('/profile/waiver/')
        form = response.context['form']
        # Form isn't valid as-is: users must add their name & email
        self.assertFalse(form.is_valid())

        with mock.patch.object(waivers, 'initiate_waiver') as initiate_waiver:
            initiate_waiver.return_value = waivers.InitiatedWaiverResult(
                email='tim@mit.edu', url=None
            )
            response = self.client.post(
                '/profile/waiver/',
                {'releasor-name': 'Tim Beaver', 'releasor-email': 'tim@mit.edu'},
                follow=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        initiate_waiver.assert_called_once_with(
            participant=None,
            releasor=waivers.Person(name='Tim Beaver', email='tim@mit.edu'),
            guardian=None,
        )
        redirected = self.client.get('/')
        self.assertEqual(
            [str(m) for m in redirected.context['messages']],
            ['Waiver sent to tim@mit.edu'],
        )

    def test_sign_as_anonymous_with_guardian(self):
        with mock.patch.object(waivers, 'initiate_waiver') as initiate_waiver:
            initiate_waiver.return_value = waivers.InitiatedWaiverResult(
                email='tim@mit.edu', url=None
            )
            response = self.client.post(
                '/profile/waiver/',
                {
                    'releasor-name': 'Tim Beaver',
                    'releasor-email': 'tim@mit.edu',
                    'guardian-name': 'Timothy Beaver, Sr',
                    'guardian-email': 'tim@alum.mit.edu',
                },
                follow=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        initiate_waiver.assert_called_once_with(
            participant=None,
            releasor=waivers.Person(name='Tim Beaver', email='tim@mit.edu'),
            guardian=waivers.Person(
                name='Timothy Beaver, Sr', email='tim@alum.mit.edu'
            ),
        )

    def test_missing_email(self):
        """Users must give their name and email."""
        with mock.patch.object(waivers, 'initiate_waiver') as initiate_waiver:
            response = self.client.post(
                '/profile/waiver/', {'releasor.name': 'Tim Beaver'}
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors['email'])
        initiate_waiver.assert_not_called()

    def test_sign_as_participant(self):
        """Participants need only visually verify their information & submit."""
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)

        dummy_embedded_url = 'https://na2.docusign.net/Signing/StartInSession.aspx?code=long-code-with-encoded-data&persistent_auth_token=no_client_token'
        with mock.patch.object(waivers, 'initiate_waiver') as initiate_waiver:
            initiate_waiver.return_value = waivers.InitiatedWaiverResult(
                email=par.email, url=dummy_embedded_url
            )
            response = self.client.post(
                '/profile/waiver/',
                # No form data is needed! Information is pre-filled.
                {},
                # Don't actually try to load our dummy URL
                follow=False,
            )

        # The participant is redirected immediately to the sign-in interface
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, dummy_embedded_url)

    def test_sign_as_participant_with_guardian(self):
        """Participants can also specify a guardian."""
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)

        dummy_embedded_url = 'https://na2.docusign.net/Signing/StartInSession.aspx?code=long-code-with-encoded-data&persistent_auth_token=no_client_token'
        with mock.patch.object(waivers, 'initiate_waiver') as initiate_waiver:
            initiate_waiver.return_value = waivers.InitiatedWaiverResult(
                email=par.email, url=dummy_embedded_url
            )
            response = self.client.post(
                '/profile/waiver/',
                # No form data is needed! Information is pre-filled.
                {
                    'guardian.name': 'Tim Beaver, Sr.',
                    'guardian.email': 'tim@alum.mit.edu',
                },
                # Don't actually try to load our dummy URL
                follow=False,
            )

        # The participant is redirected immediately to the sign-in interface
        # Guardian info is given to DocuSign
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, dummy_embedded_url)
