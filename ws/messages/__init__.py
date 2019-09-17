"""
Functions that take a request, create messages if applicable.

Some messages may be called on *every* request, others as needed.
"""
from django.contrib import messages
from django.contrib.messages.storage.base import Message


class MessageGenerator:
    def __init__(self, request):
        self.request = request

    def supply(self):
        """ Supply all messages for this request. """
        raise NotImplementedError

    def add_unique_message(self, level, message, **kwargs):
        """ Add a message, but only after first making sure it's not already been emitted.

        This helps guard against any message generator adding the same message
        multiple times before the next time the messages are displayed. Once messages
        are displayed, `used` is set on the storage object returned by
        `get_messages()` and the queue is cleared.

        Returns True if message was sent for the first time.
        """
        expected = Message(message=message, level=level, **kwargs)
        if any(msg == expected for msg in messages.get_messages(self.request)):
            return False

        messages.add_message(self.request, level, message, **kwargs)
        return True
