from typing import ClassVar
from unittest import mock

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from ws import models
from ws.messages import security
from ws.middleware import CustomMessagesMiddleware, ParticipantMiddleware
from ws.tests import TestCase
from ws.tests.factories import ParticipantFactory, UserFactory


class ParticipantMiddlewareTests(TestCase):
    user: ClassVar[models.User]

    def setUp(self):
        def get_response(request):
            return None

        self.pm = ParticipantMiddleware(get_response)
        self.request = RequestFactory().get('/')

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()

    def test_anonymous_user(self):
        """When the user is anonymous, request.participant is None."""
        self.request.user = AnonymousUser()
        self.pm(self.request)
        self.assertEqual(self.request.participant, None)

    def test_authenticated_user(self):
        """Participant is None when the user hasn't yet created one."""
        self.request.user = self.user
        self.pm(self.request)
        self.assertEqual(self.request.participant, None)

    def test_user_with_participant(self):
        """When the user has created a participant, it's injected into the request."""
        self.request.user = self.user
        participant = ParticipantFactory.create(user_id=self.user.pk)

        self.pm(self.request)
        self.assertEqual(self.request.participant, participant)


class CustomMessagesMiddlewareTests(TestCase):
    user: ClassVar[models.User]

    def setUp(self):
        def get_response(request):
            return None

        self.cm = CustomMessagesMiddleware(get_response)
        self.request = RequestFactory().get('/')

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()

    def test_anonymous_user(self):
        """No messages are generated on anonymous users."""
        self.request.user = AnonymousUser()
        self.request.participant = None
        with mock.patch.object(security.messages, 'add_message') as add_message:
            self.cm(self.request)
        add_message.assert_not_called()

    def test_authenticated_user(self):
        """No messages are generated on users without a participant."""
        self.request.user = self.user
        self.request.participant = None
        with mock.patch.object(security.messages, 'add_message') as add_message:
            self.cm(self.request)
        add_message.assert_not_called()

    def test_participant_with_insecure_password(self):
        """A participant with an insecure password will have a message generated."""
        self.request.user = self.user
        self.request.participant = ParticipantFactory.create(
            user_id=self.user.pk, insecure_password=True
        )

        with mock.patch.object(security.messages, 'add_message') as add_message:
            self.cm(self.request)
        add_message.assert_called_once()

    def test_participant_with_secure_password(self):
        """A participant with secure password will have no messages generated."""
        self.request.user = self.user
        self.request.participant = ParticipantFactory.create(
            user_id=self.user.pk, insecure_password=False
        )

        with mock.patch.object(security.messages, 'add_message') as add_message:
            self.cm(self.request)
        add_message.assert_not_called()
