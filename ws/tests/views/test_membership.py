from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo

import responses
from bs4 import BeautifulSoup
from django.test import TestCase
from freezegun import freeze_time

from ws import forms, waivers
from ws.tests import factories, strip_whitespace


class RefreshMembershipViewTest(TestCase):
    def setUp(self):
        with freeze_time("2022-06-01 12:00 UTC"):
            self.participant = factories.ParticipantFactory.create(
                email="some-random-participant@example.com",
            )
        self.url = f"/participants/{self.participant.pk}/membership/"

    def test_anonymous_user(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/accounts/login/?next={self.url}")

    @responses.activate
    def test_geardb_down(self):
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)

        responses.get(
            "https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email=some-random-participant@example.com",
            status=500,
        )
        self.assertEqual(
            self.participant.membership.last_cached,
            datetime(2022, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC")),
        )

        with freeze_time("2022-06-02 13:45 UTC"):
            response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"/participants/{self.participant.pk}/",
        )

        # The cache wasn't updated
        self.assertEqual(
            self.participant.membership.last_cached,
            datetime(2022, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC")),
        )

    @freeze_time("2022-06-02 13:45 UTC")
    def test_get(self):
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)

        self.assertEqual(
            self.participant.membership.last_cached,
            datetime(2022, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC")),
        )
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.GET,
                "https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email=some-random-participant@example.com",
                json={
                    "count": 0,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "email": "some-random-participant@example.com",
                            "alternate_emails": ["other@mit.edu"],
                            "membership": {
                                "membership_type": "NA",
                                "expires": "2023-06-02",
                            },
                            "waiver": {"expires": "2023-05-04"},
                        }
                    ],
                },
                status=200,
            )
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"/participants/{self.participant.pk}/",
        )

        self.participant.membership.refresh_from_db()
        self.assertEqual(
            self.participant.membership.last_cached,
            datetime(2022, 6, 2, 13, 45, 0, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(
            self.participant.membership.membership_expires, date(2023, 6, 2)
        )

    @freeze_time("2022-06-02 13:45 UTC")
    def test_post(self):
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)

        self.assertEqual(
            self.participant.membership.last_cached,
            datetime(2022, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("UTC")),
        )
        with responses.RequestsMock() as rsps:
            rsps.add(
                responses.GET,
                "https://mitoc-gear.mit.edu/api-auth/v1/membership_waiver/?email=some-random-participant@example.com",
                json={
                    "count": 0,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "email": "some-random-participant@example.com",
                            "alternate_emails": ["other@mit.edu"],
                            "membership": {
                                "membership_type": "NA",
                                "expires": "2023-06-02",
                            },
                            "waiver": {"expires": "2023-05-04"},
                        }
                    ],
                },
                status=200,
            )
            response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            f"/participants/{self.participant.pk}/",
        )

        self.participant.membership.refresh_from_db()
        self.assertEqual(
            self.participant.membership.last_cached,
            datetime(2022, 6, 2, 13, 45, 0, tzinfo=ZoneInfo("UTC")),
        )
        self.assertEqual(
            self.participant.membership.membership_expires, date(2023, 6, 2)
        )


class PayDuesTests(TestCase):
    def test_load_form_as_anonymous_user(self):
        """Several hidden inputs are pre-filled for all members."""
        response = self.client.get("/profile/membership/")
        form = response.context["form"]

        self.assertEqual(form.fields["merchant_id"].initial, "mit_sao_mitoc")
        self.assertEqual(form.fields["description"].initial, "membership fees.")

        # merchant* fields have special meaning for CyberSource.
        # - The `'membership'` label is expected in mitoc-aws' Lambdas
        # The Affiliation is also used to create the membership record
        self.assertEqual(form.fields["merchantDefinedData1"].initial, "membership")
        self.assertEqual(
            form.fields["merchantDefinedData2"].choices,
            [
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
            ],
        )

        # The user must self report their name, email address, and affiliation
        self.assertEqual(form.fields["amount"].initial, "")
        self.assertIsNone(form.fields["merchantDefinedData3"].initial)
        self.assertIsNone(form.fields["merchantDefinedData4"].initial)

    def test_load_form_as_logged_in_participant(self):
        """We pre-populate the form for participants with information on file."""
        par = factories.ParticipantFactory.create(
            name="Timothy Beaver",
            user=factories.UserFactory.create(email="tim@mit.edu"),
            affiliation="MA",
        )
        self.client.force_login(par.user)
        response = self.client.get("/profile/membership/")
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]

        self.assertEqual(form.fields["merchant_id"].initial, "mit_sao_mitoc")
        self.assertEqual(form.fields["description"].initial, "membership fees.")
        self.assertEqual(form.fields["amount"].initial, 30)  # Annual affiliate dues
        self.assertEqual(form.fields["merchantDefinedData1"].initial, "membership")
        self.assertEqual(form.fields["merchantDefinedData2"].initial, "MA")
        self.assertEqual(form.fields["merchantDefinedData3"].initial, "tim@mit.edu")
        self.assertEqual(form.fields["merchantDefinedData4"].initial, "Timothy Beaver")

    @freeze_time("2021-12-10 12:00:00 EST")
    def test_load_form_as_member_able_to_renew(self):
        """We clearly communicate when membership ends if you renew."""
        par = factories.ParticipantFactory.create(
            membership__membership_expires=date(2021, 12, 25)
        )
        self.assertTrue(par.membership.in_early_renewal_period)
        self.client.force_login(par.user)

        response = self.client.get("/profile/membership/")

        soup = BeautifulSoup(response.content, "html.parser")
        lead_par = soup.find("p", class_="lead")
        self.assertEqual(
            lead_par.text,
            "To make the most of MITOC, you must be up-to-date on annual dues.",
        )
        self.assertEqual(
            strip_whitespace(lead_par.find_next("p").text),
            "Renewing today keeps your account active until Dec 25, 2022. "
            "Staying current on dues enables you to rent gear from the office, participate in upcoming trips, and stay at MITOC's cabins.",
        )

    @freeze_time("2021-12-10 12:00:00 EST")
    def test_load_form_as_lapsed_member(self):
        par = factories.ParticipantFactory.create(
            membership__membership_expires=date(2021, 1, 2)
        )
        self.assertFalse(par.membership.in_early_renewal_period)
        self.assertEqual(par.membership.expiry_if_paid_today, date(2022, 12, 10))

        self.client.force_login(par.user)

        response = self.client.get("/profile/membership/")

        soup = BeautifulSoup(response.content, "html.parser")
        lead_par = soup.find("p", class_="lead")
        self.assertEqual(
            lead_par.text,
            "To make the most of MITOC, you must be up-to-date on annual dues.",
        )
        self.assertEqual(
            strip_whitespace(lead_par.find_next("p").text),
            "Dues are valid for 365 days. Paying dues enables you to "
            "rent gear from the office, participate in upcoming trips, and stay at MITOC's cabins.",
        )

    def test_pay_anonymously(self):
        """Users need not log in to pay dues."""
        valid_form_data = {
            "merchant_id": "mit_sao_mitoc",
            "description": "membership fees.",
            "merchantDefinedData1": "membership",
            "merchantDefinedData2": "NA",
            "merchantDefinedData3": "tim@mit.edu",
            "merchantDefinedData4": "Tim Beaver",
            "amount": 40,
        }

        # If this were a normal form view, the values above would be accepted
        self.assertTrue(forms.DuesForm(valid_form_data, participant=None).is_valid())

        # We can't test that CyberSource accepts the payload, so stop here


class SignWaiverTests(TestCase):
    def test_sign_as_anonymous_user(self):
        """You don't need to be logged in to sign a waiver."""
        response = self.client.get("/profile/waiver/")
        form = response.context["form"]
        # Form isn't valid as-is: users must add their name & email
        self.assertFalse(form.is_valid())

        with mock.patch.object(waivers, "initiate_waiver") as initiate_waiver:
            initiate_waiver.return_value = waivers.InitiatedWaiverResult(
                email="tim@mit.edu", url=None
            )
            response = self.client.post(
                "/profile/waiver/",
                {"releasor-name": "Tim Beaver", "releasor-email": "tim@mit.edu"},
                follow=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")
        initiate_waiver.assert_called_once_with(
            participant=None,
            releasor=waivers.Person(name="Tim Beaver", email="tim@mit.edu"),
            guardian=None,
        )
        redirected = self.client.get("/")
        self.assertEqual(
            [str(m) for m in redirected.context["messages"]],
            ["Waiver sent to tim@mit.edu"],
        )

    def test_sign_as_anonymous_with_guardian(self):
        with mock.patch.object(waivers, "initiate_waiver") as initiate_waiver:
            initiate_waiver.return_value = waivers.InitiatedWaiverResult(
                email="tim@mit.edu", url=None
            )
            response = self.client.post(
                "/profile/waiver/",
                {
                    "releasor-name": "Tim Beaver",
                    "releasor-email": "tim@mit.edu",
                    "guardian-name": "Timothy Beaver, Sr",
                    "guardian-email": "tim@alum.mit.edu",
                },
                follow=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")
        initiate_waiver.assert_called_once_with(
            participant=None,
            releasor=waivers.Person(name="Tim Beaver", email="tim@mit.edu"),
            guardian=waivers.Person(
                name="Timothy Beaver, Sr", email="tim@alum.mit.edu"
            ),
        )

    def test_missing_email(self):
        """Users must give their name and email."""
        with mock.patch.object(waivers, "initiate_waiver") as initiate_waiver:
            response = self.client.post(
                "/profile/waiver/", {"releasor.name": "Tim Beaver"}
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors["email"])
        initiate_waiver.assert_not_called()

    def test_sign_as_participant(self):
        """Participants need only visually verify their information & submit."""
        par = factories.ParticipantFactory.create()
        self.client.force_login(par.user)

        dummy_embedded_url = "https://na2.docusign.net/Signing/StartInSession.aspx?code=long-code-with-encoded-data&persistent_auth_token=no_client_token"
        with mock.patch.object(waivers, "initiate_waiver") as initiate_waiver:
            initiate_waiver.return_value = waivers.InitiatedWaiverResult(
                email=par.email, url=dummy_embedded_url
            )
            response = self.client.post(
                "/profile/waiver/",
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

        dummy_embedded_url = "https://na2.docusign.net/Signing/StartInSession.aspx?code=long-code-with-encoded-data&persistent_auth_token=no_client_token"
        with mock.patch.object(waivers, "initiate_waiver") as initiate_waiver:
            initiate_waiver.return_value = waivers.InitiatedWaiverResult(
                email=par.email, url=dummy_embedded_url
            )
            response = self.client.post(
                "/profile/waiver/",
                # No form data is needed! Information is pre-filled.
                {
                    "guardian.name": "Tim Beaver, Sr.",
                    "guardian.email": "tim@alum.mit.edu",
                },
                # Don't actually try to load our dummy URL
                follow=False,
            )

        # The participant is redirected immediately to the sign-in interface
        # Guardian info is given to DocuSign
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, dummy_embedded_url)
