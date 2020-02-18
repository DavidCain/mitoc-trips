import re

from django.test import TestCase as DjangoTestCase

WHITESPACE = re.compile(r'[\n\s]+')


def strip_whitespace(text):
    return re.sub(WHITESPACE, ' ', text).strip()


class TestCase(DjangoTestCase):
    """ Ensures multi-database behavior is always configured!

    Any unit test that deals with authentication affects the `auth_user`
    database. To ensure that tests can query that database (and that the
    database will be rolled back along with the default database, we must set
    databases). This class does that automatically (it's very easy to forget).
    """

    # Don't bother with `geardb` by default unless test explicitly needs it!
    # Tests that need to hit `geardb` should specify that directly.
    # A broader project is to stop querying `geardb` directly and move to an API instead.
    databases = {'auth_db', 'default'}
