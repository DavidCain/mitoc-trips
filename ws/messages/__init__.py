"""
Functions that take a request, create messages if applicable.

Some messages may be called on *every* request, others as needed.
"""


class MessageGenerator:
    def __init__(self, request):
        self.request = request

    def supply(self):
        """ Supply all messages for this request. """
        raise NotImplementedError
