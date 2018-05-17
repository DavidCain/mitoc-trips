from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from ws.middleware import ParticipantMiddleware
from ws.tests.helpers import PermHelpers


class TestParticipantMiddleware(TestCase):
    def setUp(self):
        def get_response(request):
            return None
        self.pm = ParticipantMiddleware(get_response)
        self.request = Mock()

    @classmethod
    def setUpTestData(cls):
        cls.user = PermHelpers.create_user()

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

    @patch('ws.models.Participant.from_user')
    def test_user_with_participant(self, from_user):
        """ When the user has created a participant, it's injected into the request."""
        self.request.user = self.user

        participant = Mock('Participant')

        def mock_from_user(request_user):
            if request_user.id != self.user.id:
                raise ValueError("Unexpected user was passed!")
            return participant

        from_user.side_effect = mock_from_user

        self.pm(self.request)
        self.assertIs(self.request.participant, participant)
