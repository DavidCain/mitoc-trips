from datetime import datetime
from zoneinfo import ZoneInfo

from allauth.account.models import EmailAddress
from django.test import SimpleTestCase, TestCase
from freezegun import freeze_time
from mitoc_const import affiliations

from ws import forms
from ws.tests import factories


class FormTests(SimpleTestCase):
    def test_amount_choices(self):
        expected = [
            (
                "Undergraduate student",
                [("MU", "MIT undergrad ($15)"), ("NU", "Non-MIT undergrad ($40)")],
            ),
            (
                "Graduate student",
                [
                    ("MG", "MIT grad student ($15)"),
                    ("NG", "Non-MIT grad student ($40)"),
                ],
            ),
            (
                "MIT",
                [
                    ("MA", "MIT affiliate (staff or faculty) ($30)"),
                    ("ML", "MIT alum (former student) ($40)"),
                ],
            ),
            ("NA", "Non-affiliate ($40)"),
        ]

        self.assertEqual(list(forms.amount_choices()), expected)

    def test_amount_choices_with_price(self):
        expected = [
            (
                "Undergraduate student",
                [(15, "MIT undergrad ($15)"), (40, "Non-MIT undergrad ($40)")],
            ),
            (
                "Graduate student",
                [(15, "MIT grad student ($15)"), (40, "Non-MIT grad student ($40)")],
            ),
            (
                "MIT",
                [
                    (30, "MIT affiliate (staff or faculty) ($30)"),
                    (40, "MIT alum (former student) ($40)"),
                ],
            ),
            (40, "Non-affiliate ($40)"),
        ]

        self.assertEqual(list(forms.amount_choices(value_is_amount=True)), expected)


class ParticipantFormTests(TestCase):
    def test_non_mit_affiliation(self):
        """It's valid to have a non-MIT email address with non-MIT affiliations."""
        user = factories.UserFactory.create()
        EmailAddress(
            user_id=user.pk, email="not_mit@example.com", primary=True, verified=True
        ).save()
        form = forms.ParticipantForm(
            data={
                "name": "Some User",
                "email": "not_mit@example.com",
                "cell_phone": "",
                "affiliation": affiliations.NON_AFFILIATE.CODE,
            },
            user=user,
        )
        self.assertTrue(form.is_valid())

    def test_mit_affiliation_without_mit_email(self):
        """You must have an MIT email address to be an MIT student."""
        user = factories.UserFactory.create()
        EmailAddress(
            user_id=user.pk,
            email="still_not_mit@example.com",
            primary=True,
            verified=True,
        ).save()
        form = forms.ParticipantForm(
            user=user,
            data={
                "name": "Some User",
                "email": "still_not_mit@example.com",
                "cell_phone": "",
                "affiliation": affiliations.MIT_UNDERGRAD.CODE,
            },
        )
        self.assertFalse(form.is_valid())


class TripFormTests(TestCase):
    @freeze_time("Wed, 16 Oct 2019 20:30:00 EST")
    def test_default_signups_close_late_week(self):
        """On a Wednesday, we just default to midnight on the night before"""
        form = forms.TripForm()
        self.assertEqual(
            form.fields["signups_close_at"].initial(),
            datetime(2019, 10, 18, 23, 59, 59, tzinfo=ZoneInfo("America/New_York")),
        )

    @freeze_time("Mon, 14 Oct 2019 12:45:00 EST")
    def test_default_signups_close_early_week(self):
        """Early week, we default to Wednesday morning."""
        form = forms.TripForm()
        self.assertEqual(
            form.fields["signups_close_at"].initial(),
            datetime(2019, 10, 16, 9, 0, 0, tzinfo=ZoneInfo("America/New_York")),
        )
