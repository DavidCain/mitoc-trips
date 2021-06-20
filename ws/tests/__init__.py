import re

from django.test import TestCase as DjangoTestCase

WHITESPACE = re.compile(r'[\n\s]+')


def strip_whitespace(text):
    return re.sub(WHITESPACE, ' ', text).strip()


class TestCase(DjangoTestCase):
    # Don't bother with `geardb` by default unless test explicitly needs it!
    # Tests that need to hit `geardb` should specify that directly.
    # A broader project is to stop querying `geardb` directly and move to an API instead.
    databases = {'default'}
