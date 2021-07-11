import re

from django.test import TestCase as DjangoTestCase

WHITESPACE = re.compile(r'[\n\s]+')


def strip_whitespace(text):
    return re.sub(WHITESPACE, ' ', text).strip()


class TestCase(DjangoTestCase):
    # Don't bother with `geardb` by default unless test explicitly needs it!
    # Though, no tests should be hitting `geardb` at all - we've deprecated support.
    databases = {'default'}
