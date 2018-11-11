from django.test import SimpleTestCase

from ws import forms


class FormTests(SimpleTestCase):
    def test_amount_choices(self):
        expected = [
            ('Undergraduate student', [
                ('MU', 'MIT undergrad ($15)'),
                ('NU', 'Non-MIT undergrad ($15)'),
            ]),
            ('Graduate student', [
                ('MG', 'MIT grad student ($15)'),
                ('NG', 'Non-MIT grad student ($15)'),
            ]),
            ('MIT', [
                ('MA', 'MIT affiliate (staff or faculty) ($20)'),
                ('ML', 'MIT alum (former student) ($25)'),
            ]),
            ('NA', 'Non-affiliate ($25)'),
        ]

        self.assertEqual(list(forms.amount_choices()), expected)

    def test_amount_choices_with_price(self):
        expected = [
            ('Undergraduate student', [
                (15, 'MIT undergrad ($15)'),
                (15, 'Non-MIT undergrad ($15)'),
            ]),
            ('Graduate student', [
                (15, 'MIT grad student ($15)'),
                (15, 'Non-MIT grad student ($15)'),
            ]),
            ('MIT', [
                (20, 'MIT affiliate (staff or faculty) ($20)'),
                (25, 'MIT alum (former student) ($25)'),
            ]),
            (25, 'Non-affiliate ($25)'),
        ]

        self.assertEqual(list(forms.amount_choices(value_is_amount=True)), expected)
