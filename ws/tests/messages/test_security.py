from contextlib import contextmanager
from unittest import mock

from django.contrib import messages
from django.contrib.auth.models import AnonymousUser

from ws.messages import security
from ws.tests.factories import ParticipantFactory, PasswordQualityFactory, UserFactory
from ws.tests.messages import MessagesTestCase


class WarnIfPasswordInsecureTests(MessagesTestCase):
    @staticmethod
    @contextmanager
    def _mock_info():
        with mock.patch.object(security.logger, 'info') as info:
            yield info

    def test_no_user_on_request(self):
        request = self.factory.get('/')

        # Simulate the effects of the ParticipantMiddleware for an anonymous user
        request.user = AnonymousUser()
        request.participant = None

        with self._mock_info() as info, self._mock_add_message() as add_message:
            security.Messages(request).supply()

        info.assert_not_called()
        add_message.assert_not_called()

    def test_user_but_no_participant_on_request(self):
        request = self.factory.get('/')

        # Simulate the effects of the ParticipantMiddleware for a known user
        request.user = UserFactory.create()
        request.participant = None

        with self._mock_info() as info, self._mock_add_message() as add_message:
            security.Messages(request).supply()

        info.assert_not_called()
        add_message.assert_not_called()

    def test_participant_with_secure_password(self):
        request = self.factory.get('/')
        # Simulate the effects of the ParticipantMiddleware for a known participant
        quality = PasswordQualityFactory.create(is_insecure=False)
        request.participant = quality.participant
        request.user = quality.participant.user

        with self._mock_info() as info, self._mock_add_message() as add_message:
            security.Messages(request).supply()

        info.assert_not_called()
        add_message.assert_not_called()

    def test_participant_with_insecure_password(self):
        """Test core behavior of the generator - a known participant with a bad password."""
        # Use the test client, since RequestFactory can't handle messages
        user = UserFactory.create(email='fake@example.com', password='password')
        par = ParticipantFactory.create(email='fake@example.com', user=user)
        PasswordQualityFactory.create(participant=par, is_insecure=True)
        self.client.login(email=user.email, password='password')

        with self._mock_info() as info, self._mock_add_message(True) as add_message:
            # Loading any page will invoke the security messages
            response = self.client.get('/contact/')
            request = response.wsgi_request

            # Explicitly re-supply messages on the same request (without a page load)
            # This will not add to the total number of calls to `add_message()`
            security.Messages(request).supply()
            security.Messages(request).supply()

        add_message.assert_called_once_with(
            request,
            messages.ERROR,
            'Your password is insecure! Please <a href="/accounts/password/change/">change your password.</a>',
            extra_tags='safe',
        )
        info.assert_called_once_with(
            "Warned participant %s (%s) about insecure password",
            par.pk,
            'fake@example.com',
        )

    def test_participant_with_insecure_password_on_change_password(self):
        """Make sure the message isn't rendered if already changing password.

        The change password template gives a full explanation of why the user's password
        is marked insecure, so there's no reason to also supply a message.
        """
        request = self.factory.get('/accounts/password/change/?query_args=are_ignored')
        quality = PasswordQualityFactory.create(is_insecure=True)
        request.participant = quality.participant
        request.user = quality.participant.user

        with self._mock_add_message() as add_message:
            security.Messages(request).supply()

        add_message.assert_not_called()
