from django.test import TestCase as DjangoTestCase


class TestCase(DjangoTestCase):
    """ Ensures multi-database behavior is always configured!

    Any unit test that deals with authentication affects the `auth_user`
    database. To ensure that this database is rolled back along with the
    default database, we must set `multi_db`. This class does that
    automatically (it's very easy to forget).
    """
    multi_db = True  # Roll back changes in _all_ databases
