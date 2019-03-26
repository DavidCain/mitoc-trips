from unittest.mock import Mock

from django.contrib.auth.models import AnonymousUser

from ws.middleware import ParticipantMiddleware
from ws.tests.factories import UserFactory, ParticipantFactory
from ws.tests import TestCase


class TestParticipantMiddleware(TestCase):
    def setUp(self):
        def get_response(request):
            return None

        self.pm = ParticipantMiddleware(get_response)
        self.request = Mock()

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()

    def test_anonymous_user(self):
        """ When the user is anonymous, request.participant is None. """
        self.request.user = AnonymousUser()
        self.pm(self.request)
        self.assertEqual(self.request.participant, None)

    def test_authenticated_user(self):
        """ Participant is None when the user hasn't yet created one. """
        self.request.user = self.user
        self.pm(self.request)
        self.assertEqual(self.request.participant, None)

    def test_user_with_participant(self):
        """ When the user has created a participant, it's injected into the request."""
        self.request.user = self.user
        participant = ParticipantFactory.create(user_id=self.user.pk)

        self.pm(self.request)
        self.assertEqual(self.request.participant, participant)
