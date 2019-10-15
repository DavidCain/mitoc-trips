from contextlib import contextmanager
from unittest import mock

from django.contrib import messages
from django.test import RequestFactory

from ws.tests import TestCase


class MessagesTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request_with_participant(self, participant):
        """ Return a real request option that behaves like participant middleware. """
        request = self.factory.get('/')
        request.user = participant.user
        request.participant = participant
        return request

    @staticmethod
    @contextmanager
    def _mock_add_message(wrap=False):
        """ Mock `add_message`.

        If `wrap` is True, then do not mock away functionality.
        (If choosing to wrap, RequestFactory should not be used - middleware
        must be present for `add_message` to work!)
        """
        kwargs = {'wraps': messages.add_message} if wrap else {}
        with mock.patch.object(messages, 'add_message', **kwargs) as add_message:
            yield add_message
