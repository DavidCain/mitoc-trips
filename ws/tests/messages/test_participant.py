from django.contrib import messages
from django.contrib.auth.models import AnonymousUser
from freezegun import freeze_time

from ws.messages.participant import Messages
from ws.tests import factories
from ws.tests.messages import MessagesTestCase


class ParticipantMessagesTest(MessagesTestCase):
    def test_anonymous_user(self):
        """ With no participant object, no messages should be emitted. """
        request = self.factory.get('/')

        # Simulate the effects of the ParticipantMiddleware for an anonymous user
        request.user = AnonymousUser()
        request.participant = None

        with self._mock_add_message() as add_message:
            Messages(request).supply()

        add_message.assert_not_called()

    def test_participant_with_current_info(self):
        """ In the usual case (participant with current info, we do nothing. """
        request = self.factory.get('/')

        par = factories.ParticipantFactory.create()
        self.assertTrue(par.info_current)  # (just created!)
        request.participant = par
        request.user = par.user

        with self._mock_add_message() as add_message:
            Messages(request).supply()

        add_message.assert_not_called()

    def test_user_but_no_participant_on_request(self):
        """ Users must have a participant in order to be on trips. """
        request = self.factory.get('/')

        # Simulate the effects of the ParticipantMiddleware for a known user
        request.user = factories.UserFactory.create()
        request.participant = None

        with self._mock_add_message() as add_message:
            Messages(request).supply()

        add_message.assert_called_once_with(
            request,
            messages.WARNING,
            '<a href="/profile/edit/">Update your profile</a> to sign up for trips.',
            extra_tags='safe',
        )

    def test_dated_participant(self):
        """ Users must have up-to-date information to go on trips. """
        request = self.factory.get('/')

        with freeze_time("2017-01-17 14:56:00 EST"):
            par = factories.ParticipantFactory.create()
        request.participant = par
        request.user = par.user

        with self._mock_add_message() as add_message:
            Messages(request).supply()

        add_message.assert_called_once_with(
            request,
            messages.WARNING,
            '<a href="/profile/edit/">Update your profile</a> to sign up for trips.',
            extra_tags='safe',
        )
