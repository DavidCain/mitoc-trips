from ws import forms
from ws.tests import TestCase, factories


class PayDuesTests(TestCase):
    def test_load_form_as_anonymous_user(self):
        """ Several hidden inputs are pre-filled for all members. """
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
        """ We pre-populate the form for participants with information on file. """
        par = factories.ParticipantFactory.create(email='tim@mit.edu', affiliation='MA')
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

    def test_pay_anonymously(self):
        """ Users need not log in to pay dues. """
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
