from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
import mock

from ws.middleware import ParticipantMiddleware
from ws.tests.helpers import PermHelpers


class TestParticipantMiddleware(TestCase):
    def setUp(self):
        def get_response(request):
            return None
        self.pm = ParticipantMiddleware(get_response)
        self.request = mock.Mock()

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

    @mock.patch('ws.models.Participant.objects.get')
    def test_user_with_participant(self, get_participant):
        """ When the user has created a participant, it's injected into the request."""
        participant = mock.Mock()
        get_participant.return_value = participant

        self.request.user = self.user
        self.pm(self.request)
        self.assertIs(self.request.participant, participant)
