from contextlib import contextmanager
from unittest import mock

from django.contrib import messages
from django.test import RequestFactory

from ws.tests import TestCase


class MessagesTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @staticmethod
    @contextmanager
    def _mock_add_message():
        with mock.patch.object(messages, 'add_message') as add_message:
            yield add_message
