from contextlib import contextmanager
from unittest import mock

from django.contrib.auth.models import AnonymousUser

from ws.messages import security
from ws.tests.factories import ParticipantFactory, UserFactory
from ws.tests.messages import MessagesTestCase


class WarnIfPasswordInsecureTests(MessagesTestCase):
    @staticmethod
    @contextmanager
    def _mock_debug():
        with mock.patch.object(security.logger, 'debug') as debug:
            yield debug

    def test_no_user_on_request(self):
        request = self.factory.get('/')

        # Simulate the effects of the ParticipantMiddleware for an anonymous user
        request.user = AnonymousUser()
        request.participant = None

        with self._mock_debug() as debug, self._mock_messages_error() as error:
            security.Messages(request).supply()

        debug.assert_not_called()
        error.assert_not_called()

    def test_user_but_no_participant_on_request(self):
        request = self.factory.get('/')

        # Simulate the effects of the ParticipantMiddleware for a known user
        request.user = UserFactory.create()
        request.participant = None

        with self._mock_debug() as debug, self._mock_messages_error() as error:
            security.Messages(request).supply()

        debug.assert_not_called()
        error.assert_not_called()

    def test_participant_with_secure_password(self):
        request = self.factory.get('/')
        # Simulate the effects of the ParticipantMiddleware for a known participant
        par = ParticipantFactory.create(insecure_password=False)
        request.participant = par
        request.user = par.user

        with self._mock_debug() as debug, self._mock_messages_error() as error:
            security.Messages(request).supply()

        debug.assert_not_called()
        error.assert_not_called()

    def test_participant_with_insecure_password(self):
        """ Test core behavior of the generator - a known participant with a bad password. """
        request = self.factory.get('/')
        par = ParticipantFactory.create(
            email='oops@example.com', insecure_password=True
        )
        request.participant = par
        request.user = par.user

        with self._mock_debug() as debug, self._mock_messages_error() as error:
            security.Messages(request).supply()

        error.assert_called_once_with(
            request,
            'Your password is insecure! Please <a href="/accounts/password/change/">change your password.</a>',
            extra_tags='safe',
        )
        debug.assert_called_once_with(
            "Warned participant %s ({%s}) about insecure password",
            par.pk,
            'oops@example.com',
        )
