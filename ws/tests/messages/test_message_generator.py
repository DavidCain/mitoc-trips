from contextlib import contextmanager
from unittest import mock

from django.contrib import messages
from django.contrib.auth.models import User

from ws.messages import MessageGenerator
from ws.tests import TestCase


class MessageGeneratorTests(TestCase):
    @staticmethod
    @contextmanager
    def _spy_on_add_message():
        patched = mock.patch.object(messages, 'add_message', wraps=messages.add_message)
        with patched as add_message:
            yield add_message

    def setUp(self):
        super().setUp()
        # We use a real client so that we can get access to messages middleware!
        user = User.objects.create_user(
            email='fake@example.com', password='password', username='username'
        )
        self.client.login(email=user.email, password='password')

    def test_supply(self):
        """ The `supply()` method must be overridden by children. """
        response = self.client.get('/')
        request = response.wsgi_request
        base_generator = MessageGenerator(request)
        with self.assertRaises(NotImplementedError):
            base_generator.supply()

    def test_add_unique_message(self):
        """ Once emitted, messages cannot be re-emitted! """
        response = self.client.get('/')
        request = response.wsgi_request
        generator = MessageGenerator(request)

        hello_call = mock.call(request, messages.INFO, "Hello")
        goodbye_call = mock.call(request, messages.INFO, "Goodbye")

        with self._spy_on_add_message() as add_message:
            # On first invocation, sends out the message
            generator.add_unique_message(messages.INFO, "Hello")
            self.assertIn(hello_call, add_message.call_args_list)
            add_message.reset_mock()

            # On second invocation, does not send again
            generator.add_unique_message(messages.INFO, "Hello")
            self.assertNotIn(hello_call, add_message.call_args_list)

            # A new unique message will be sent, though!
            generator.add_unique_message(messages.INFO, "Goodbye")
            self.assertIn(goodbye_call, add_message.call_args_list)
