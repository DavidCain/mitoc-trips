import uuid
from datetime import datetime
from unittest import mock

import allauth.account.models as account_models
import pytz
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from freezegun import freeze_time
from pwned_passwords_django import api

from ws import models
from ws.tests import TestCase, factories
from ws.views import account


@freeze_time("2019-08-29 12:25:00 EST")
class LoginTests(TestCase):
    def setUp(self):
        super().setUp()
        # Make a user with a terrible, very-often breached password
        self.user = User.objects.create_user(
            username='hacked', email='hacked@example.com', password='football'
        )
        account_models.EmailAddress.objects.create(
            email=self.user.email, verified=True, primary=True, user_id=self.user.pk
        )
        self.form_data = {'login': 'hacked@example.com', 'password': 'football'}

    def _login(self):
        return self.client.post('/accounts/login/', self.form_data, follow=False)

    def test_previously_insecure_password_marked_secure(self):
        """ A previously-marked insecure password can be marked as secure on login.

        Once a password is detected to be breached, it's not as if it would
        ever be *removed* from the database. That said, if there's an API
        outage, we'd rather mark people as having secure passwords than block
        them from using the site (we'll check again on their next login).
        """
        factories.ParticipantFactory.create(
            user_id=self.user.pk, insecure_password=True
        )
        with mock.patch.object(account, 'pwned_password') as pwned_password:
            pwned_password.return_value = None  # (API was down)
            response = self._login()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

        pwned_password.assert_called_once_with('football')

        participant = models.Participant.from_user(self.user)
        self.assertFalse(participant.insecure_password)

        # Because the API was down, we did not write to `password_last_checked`
        self.assertIsNone(participant.password_last_checked)

    def test_previously_secure_password(self):
        """ The database is updated all the time - any user's password can become compromised! """
        factories.ParticipantFactory.create(
            user_id=self.user.pk, insecure_password=False
        )
        with mock.patch.object(account, 'pwned_password') as pwned_password:
            pwned_password.return_value = 15  # password found in 15 separate breaches!
            with mock.patch.object(account.logger, 'info') as logger_info:
                response = self._login()

        pwned_password.assert_called_once_with('football')
        participant = models.Participant.from_user(self.user)
        logger_info.assert_called_once_with(
            "%s logged in with a breached password", f"Participant {participant.pk}"
        )

        # The participant's password was found to be in breaches, so we update the record!
        self.assertTrue(participant.insecure_password)
        self.assertEqual(
            participant.password_last_checked,
            datetime(2019, 8, 29, 16, 25, tzinfo=pytz.utc),
        )

        # Because the user's password is insecure, they're prompted to change it
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/password/change/")

    def test_user_without_participant(self):
        """ Users may log in without having an associated participant! """
        self.assertIsNone(models.Participant.from_user(self.user))

        with mock.patch.object(account, 'pwned_password') as pwned_password:
            pwned_password.return_value = 1  # password found in 1 breach!
            with mock.patch.object(account.logger, 'info') as logger_info:
                response = self._login()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/password/change/")

        redirected_response = self.client.get(response.url)
        logger_info.assert_called_once_with(
            "%s logged in with a breached password", f"User {self.user.pk}"
        )
        pwned_password.assert_called_once_with('football')

        soup = BeautifulSoup(redirected_response.content, 'html.parser')
        alert = soup.find(class_='alert-danger')
        # Because the user's password is insecure, they're prompted to change it
        self.assertIn(
            'This password has been compromised! Please choose a new password.',
            alert.get_text(),
        )

    def test_password_is_marked_secure(self):
        """ If the login's password returned no breaches, then we can mark it secure. """
        factories.ParticipantFactory.create(user_id=self.user.pk)

        with mock.patch.object(account, 'pwned_password') as pwned_password:
            pwned_password.return_value = 0  # (0 breaches total)
            response = self.client.post('/accounts/login/', self.form_data)
        pwned_password.assert_called_once_with('football')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

        participant = models.Participant.from_user(self.user)

        # The participant's password was found to be in zero breaches, so we update the record!
        self.assertFalse(participant.insecure_password)
        self.assertEqual(
            participant.password_last_checked,
            datetime(2019, 8, 29, 16, 25, tzinfo=pytz.utc),
        )

    def test_redirect_should_be_preserved(self):
        """ If attempting to login with a redirect, it should be preserved!. """
        with mock.patch.object(account, 'pwned_password') as pwned_password:
            pwned_password.return_value = 1  # Password has been breached once!
            response = self.client.post(
                '/accounts/login/?next=/preferences/lottery/', self.form_data
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
        self.user = User.objects.create_user(
            username='strong', email='strong@example.com', password=self.password
        )
        account_models.EmailAddress.objects.create(
            email=self.user.email, verified=True, primary=True, user_id=self.user.pk
        )

    def _change_password(self, new_password):
        form_data = {
            'oldpassword': self.password,
            'password1': new_password,
            'password2': new_password,
        }
        return self.client.post('/accounts/password/change/', form_data, follow=False)

    def test_change_password_fram_insecure(self):
        """ Changing an insecure password to a secure one updates the participant. """
        factories.ParticipantFactory.create(
            user_id=self.user.pk, insecure_password=True
        )
        # Simulate login (skip the normal login flow)
        self.client.login(email='strong@example.com', password=self.password)
        new_password = str(uuid.uuid4())

        # The form validation will invoke pwned_password
        with mock.patch.object(api, 'pwned_password') as pwned_password:
            pwned_password.return_value = 0  # (0 breaches total)
            response = self._change_password(new_password)

        self.assertEqual(response.status_code, 302)
        pwned_password.assert_called_once_with(new_password)

        participant = models.Participant.from_user(self.user)
        # The participant's password was found to be in zero breaches, so we update the record!
        self.assertFalse(participant.insecure_password)
        self.assertEqual(
            participant.password_last_checked,
            datetime(2019, 7, 15, 16, 45, tzinfo=pytz.utc),
        )

    def test_user_without_participant(self):
        """ It's possible for users to change password as a user without a participant. """
        user = User.objects.create_user(
            username='bad', email='bad@example.com', password=self.password
        )
        account_models.EmailAddress.objects.create(
            email=user.email, verified=True, primary=True, user_id=user.pk
        )

        # Skip the normal login flow, so we're only validating on the change flow
        self.client.login(email='bad@example.com', password=self.password)

        new_password = str(uuid.uuid4())

        # The form validation will invoke pwned_password
        with mock.patch.object(api, 'pwned_password') as pwned_password:
            pwned_password.return_value = 0  # (0 breaches total)
            response = self._change_password(new_password)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/")
        pwned_password.assert_called_once_with(new_password)

        # There is no participant record for the user
        self.assertIsNone(models.Participant.from_user(user))

    def test_attempt_changing_to_insecure_password(self):
        """ The password validator will stop insecure passwords from being accepted. """
        factories.ParticipantFactory.create(
            user_id=self.user.pk, insecure_password=False
        )
        # Simulate login (skip the normal login flow)
        self.client.login(email='strong@example.com', password=self.password)
        new_insecure_password = 'letmeinplease'

        # The form validation will invoke pwned_password
        with mock.patch.object(api, 'pwned_password') as pwned_password:
            pwned_password.return_value = 12
            response = self._change_password(new_insecure_password)

        self.assertEqual(response.status_code, 200)
        pwned_password.assert_called_once_with('letmeinplease')

        soup = BeautifulSoup(response.content, 'html.parser')
        errorlist = soup.find(class_='errorlist')
        self.assertTrue(errorlist)
        self.assertTrue(errorlist.find(text='This password is too common.'))
