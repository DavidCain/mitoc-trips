from django.test import SimpleTestCase

from ws import forms


class FormTests(SimpleTestCase):
    def test_amount_choices(self):
        expected = [
            ('Undergraduate student', [
                ('MU', 'MIT undergrad ($15)'),
                ('NU', 'Non-MIT undergrad ($40)'),
            ]),
            ('Graduate student', [
                ('MG', 'MIT grad student ($15)'),
                ('NG', 'Non-MIT grad student ($40)'),
            ]),
            ('MIT', [
                ('MA', 'MIT affiliate (staff or faculty) ($30)'),
                ('ML', 'MIT alum (former student) ($40)'),
            ]),
            ('NA', 'Non-affiliate ($40)'),
        ]

        self.assertEqual(list(forms.amount_choices()), expected)

    def test_amount_choices_with_price(self):
        expected = [
            ('Undergraduate student', [
                (15, 'MIT undergrad ($15)'),
                (40, 'Non-MIT undergrad ($40)'),
            ]),
            ('Graduate student', [
                (15, 'MIT grad student ($15)'),
                (40, 'Non-MIT grad student ($40)'),
            ]),
            ('MIT', [
                (30, 'MIT affiliate (staff or faculty) ($30)'),
                (40, 'MIT alum (former student) ($40)'),
            ]),
            (40, 'Non-affiliate ($40)'),
        ]

        self.assertEqual(list(forms.amount_choices(value_is_amount=True)), expected)
