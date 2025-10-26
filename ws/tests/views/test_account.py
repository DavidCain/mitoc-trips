import uuid
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from django.test import TestCase
from freezegun import freeze_time
from pwned_passwords_django import api, exceptions

from ws import auth, models
from ws.tests import factories
from ws.views import account


@freeze_time("2019-08-29 12:25:00 EST")
class LoginTests(TestCase):
    def setUp(self):
        super().setUp()
        # Make a user with a terrible, very-often breached password
        self.user = factories.UserFactory.create(
            email="hacked@example.com",
            password="football",  # noqa: S106
        )
        self.form_data = {"login": "hacked@example.com", "password": "football"}

    def _login(self):
        return self.client.post("/accounts/login/", self.form_data, follow=False)

    def test_previously_insecure_password_marked_secure(self):
        """A previously-marked insecure password can be marked as secure on login.

        Once a password is detected to be breached, it's not as if it would
        ever be *removed* from the database. That said, if there's an API
        outage, we'd rather mark people as having secure passwords than block
        them from using the site (we'll check again on their next login).
        """
        par = factories.ParticipantFactory.create(user=self.user)
        factories.PasswordQualityFactory.create(participant=par, is_insecure=True)
        with mock.patch.object(api, "check_password") as check_password:
            check_password.side_effect = exceptions.PwnedPasswordsError(
                message="Pwned Passwords API replied with HTTP error status code.",
                code=exceptions.ErrorCode.HTTP_ERROR,
                params={"status_code": 503},
            )
            response = self._login()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

        check_password.assert_called_once_with("football")

        quality = models.PasswordQuality.objects.get(participant=par)
        self.assertFalse(quality.is_insecure)

        # Because the API was down, we did not write that we checked the password
        self.assertIsNone(quality.last_checked)

    @mock.patch.object(auth, "settings")
    def test_known_bad_password(self, mocked_settings):
        """We include a debug mode that supports passing known bad passwords."""
        par = factories.ParticipantFactory.create(user_id=self.user.pk)

        # We only sidestep the API if `DEBUG` is true, and our password is whitelisted!
        mocked_settings.DEBUG = True
        mocked_settings.ALLOWED_BAD_PASSWORDS = ("football",)

        with mock.patch.object(api, "check_password") as check_password:
            response = self.client.post("/accounts/login/", self.form_data)

        # We don't bother hitting the API!
        check_password.assert_not_called()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

        quality = models.PasswordQuality.objects.get(participant=par)
        # The participant's password was hard-coded to be in zero breaches, so we update the record!
        self.assertFalse(quality.is_insecure)
        self.assertEqual(
            quality.last_checked,
            datetime(2019, 8, 29, 16, 25, tzinfo=ZoneInfo("UTC")),
        )

        # Log in again, but this time with DEBUG off (& whitelist still present)
        # Even with the whitelist, it's not honored unless DEBUG mode is on.
        self.client.logout()
        mocked_settings.DEBUG = False
        self.assertEqual(mocked_settings.ALLOWED_BAD_PASSWORDS, ("football",))

        # This time, we hit the API and mark the user as having an insecure password.
        with mock.patch.object(api, "check_password") as check_password:
            check_password.return_value = 2022
            response = self.client.post("/accounts/login/", self.form_data)
        check_password.assert_called_once_with("football")
        participant = models.Participant.from_user(self.user)
        self.assertTrue(participant.passwordquality.is_insecure)

    def test_previously_secure_password(self):
        """The database is updated all the time - any user's password can become compromised!"""
        participant = factories.ParticipantFactory.create(user=self.user)
        factories.PasswordQualityFactory.create(
            participant=participant, is_insecure=True
        )
        with mock.patch.object(api, "check_password") as check_password:
            check_password.return_value = 15  # password found in 15 separate breaches!
            with mock.patch.object(account.logger, "info") as logger_info:
                response = self._login()

        check_password.assert_called_once_with("football")
        logger_info.assert_called_once_with(
            "Participant %s logged in with a breached password", participant.pk
        )

        # The participant's password was found to be in breaches, so we update the record!
        quality = models.PasswordQuality.objects.get(participant=participant)
        self.assertTrue(quality.is_insecure)
        self.assertEqual(
            quality.last_checked,
            datetime(2019, 8, 29, 16, 25, tzinfo=ZoneInfo("UTC")),
        )

        # Because the user's password is insecure, they're prompted to change it
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/password/change/")

    def test_user_without_participant(self):
        """Users may log in without having an associated participant!"""
        self.assertIsNone(models.Participant.from_user(self.user))

        with mock.patch.object(api, "check_password") as check_password:
            check_password.return_value = 1  # password found in 1 breach!
            with mock.patch.object(account.logger, "info") as logger_info:
                response = self._login()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/password/change/")

        redirected_response = self.client.get(response.url)
        logger_info.assert_called_once_with(
            "User %s logged in with a breached password", self.user.pk
        )
        check_password.assert_called_once_with("football")

        soup = BeautifulSoup(redirected_response.content, "html.parser")
        alert = soup.find(class_="alert-danger")
        # Because the user's password is insecure, they're prompted to change it
        self.assertIn(
            "This password has been compromised! Please choose a new password.",
            alert.get_text(),
        )

    def test_password_is_marked_secure(self):
        """If the login's password returned no breaches, then we can mark it secure."""
        factories.ParticipantFactory.create(user_id=self.user.pk)

        with mock.patch.object(api, "check_password") as check_password:
            check_password.return_value = 0  # (0 breaches total)
            response = self.client.post("/accounts/login/", self.form_data)
        check_password.assert_called_once_with("football")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

        participant = models.Participant.from_user(self.user)

        # The participant's password was found to be in zero breaches, so we update the record!
        self.assertFalse(participant.passwordquality.is_insecure)
        self.assertEqual(
            participant.passwordquality.last_checked,
            datetime(2019, 8, 29, 16, 25, tzinfo=ZoneInfo("UTC")),
        )

    def test_redirect_should_be_preserved(self):
        """If attempting to login with a redirect, it should be preserved!."""
        with mock.patch.object(api, "check_password") as check_password:
            check_password.return_value = 1  # Password has been breached once!
            response = self.client.post(
                "/accounts/login/?next=/preferences/lottery/", self.form_data
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, "/accounts/password/change/?next=%2Fpreferences%2Flottery%2F"
        )


@freeze_time("2019-07-15 12:45:00 EST")
class PasswordChangeTests(TestCase):
    def setUp(self):
        super().setUp()

        self.password = str(uuid.uuid4())  # A long, sufficiently random password!
        self.user = factories.UserFactory.create(
            email="strong@example.com", password=self.password
        )

    def _change_password(self, new_password):
        form_data = {
            "oldpassword": self.password,
            "password1": new_password,
            "password2": new_password,
        }
        return self.client.post("/accounts/password/change/", form_data, follow=False)

    def test_change_password_from_insecure(self):
        """Changing an insecure password to a secure one updates the participant."""
        par = factories.ParticipantFactory.create(user=self.user)
        factories.PasswordQualityFactory.create(participant=par, is_insecure=True)
        # Simulate login (skip the normal login flow)
        self.client.login(email="strong@example.com", password=self.password)
        new_password = str(uuid.uuid4())

        # The form validation will invoke check_password
        with mock.patch.object(api.PwnedPasswords, "check_password") as check_password:
            check_password.return_value = 0  # (0 breaches total)
            response = self._change_password(new_password)

        self.assertEqual(response.status_code, 302)
        check_password.assert_called_once_with(new_password)

        par.passwordquality.refresh_from_db()
        # The participant's password was found to be in zero breaches, so we update the record!
        self.assertFalse(par.passwordquality.is_insecure)
        self.assertEqual(
            par.passwordquality.last_checked,
            datetime(2019, 7, 15, 16, 45, tzinfo=ZoneInfo("UTC")),
        )

    def test_user_without_participant(self):
        """It's possible for users to change password as a user without a participant."""
        user = factories.UserFactory.create(
            email="bad@example.com", password=self.password
        )

        # Skip the normal login flow, so we're only validating on the change flow
        self.client.login(email="bad@example.com", password=self.password)

        new_password = str(uuid.uuid4())

        # The form validation will invoke check_password
        with mock.patch.object(api.PwnedPasswords, "check_password") as check_password:
            check_password.return_value = 0  # (0 breaches total)
            response = self._change_password(new_password)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/")
        check_password.assert_called_once_with(new_password)

        # There is no participant record for the user
        self.assertIsNone(models.Participant.from_user(user))

    def test_attempt_changing_to_insecure_password(self):
        """The password validator will stop insecure passwords from being accepted."""
        par = factories.ParticipantFactory.create(user=self.user)
        factories.PasswordQualityFactory.create(participant=par, is_insecure=False)
        # Simulate login (skip the normal login flow)
        self.client.login(email="strong@example.com", password=self.password)
        new_insecure_password = "letmeinplease"  # noqa: S105

        # The form validation will invoke check_password
        with mock.patch.object(api.PwnedPasswords, "check_password") as check_password:
            check_password.return_value = 12
            response = self._change_password(new_insecure_password)

        self.assertEqual(response.status_code, 200)
        check_password.assert_called_once_with("letmeinplease")

        soup = BeautifulSoup(response.content, "html.parser")
        form_group = soup.find(class_="has-error")
        self.assertTrue(form_group)
        self.assertTrue(form_group.find(string="This password is too common."))


class ManageEmailsTest(TestCase):
    maxDiff = None

    def _get_buttons(self, user):
        self.client.force_login(user)
        response = self.client.get("/accounts/email/")
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", action="/accounts/email/")
        return {btn.text.strip(): btn.attrs for btn in form.find_all("button")}

    def test_one_primary_email(self):
        """Test the usual case -- just one verified primary email."""
        user = factories.UserFactory.create(
            emailaddress__primary=True,
            emailaddress__verified=True,
        )

        self.assertEqual(
            self._get_buttons(user),
            {
                "Make Primary": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "disabled": "",
                    "title": "Email address is already primary.",
                    "name": "action_primary",
                },
                # Notably "Re-send Verification" is missing entirely
                "Remove": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "disabled": "",
                    "title": "Cannot remove your only email address.",
                    "name": "action_remove",
                },
            },
        )

    def test_one_unverified_email(self):
        user = factories.UserFactory.create(emailaddress__verified=False)

        self.assertEqual(
            self._get_buttons(user),
            {
                "Make Primary": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "disabled": "",
                    "title": "Email address is already primary.",
                    "name": "action_primary",
                },
                "Re-send Verification": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_send",
                },
                "Remove": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "disabled": "",
                    "title": "Cannot remove your only email address.",
                    "name": "action_remove",
                },
            },
        )

    def test_two_verified_emails(self):
        """With two emails, we can remove either or make either primary."""
        user = factories.UserFactory.create()
        factories.EmailAddressFactory.create(
            user=user,
            email="some.other.email@example.com",
            primary=False,
            verified=True,
        )

        self.assertEqual(
            self._get_buttons(user),
            {
                "Make Primary": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_primary",
                },
                # Notably "Re-send Verification" is missing entirely -- both are verified!
                "Remove": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_remove",
                },
            },
        )

    def test_two_emails_but_one_unverified(self):
        """Test the case of a newly-added but still unverified email."""
        user = factories.UserFactory.create(
            emailaddress__verified=True,
        )
        factories.EmailAddressFactory.create(
            user=user,
            email="some.other.email@example.com",
            primary=False,
            verified=False,
        )

        self.assertEqual(
            self._get_buttons(user),
            {
                "Make Primary": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_primary",
                },
                # Because there's at least one unverified email, we allow re-sending
                "Re-send Verification": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_send",
                },
                "Remove": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_remove",
                },
            },
        )

    def test_multiple_unverified(self):
        """You can still add an email even if one is unverified!"""
        user = factories.UserFactory.create()
        factories.EmailAddressFactory.create(
            user=user,
            email="some.other.email@example.com",
            primary=False,
            verified=False,
        )

        self.assertEqual(
            self._get_buttons(user),
            {
                "Make Primary": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_primary",
                },
                # Because there's at least one unverified email, we allow re-sending
                "Re-send Verification": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_send",
                },
                "Remove": {
                    "class": ["btn", "btn-default"],
                    "type": "submit",
                    "name": "action_remove",
                },
            },
        )
