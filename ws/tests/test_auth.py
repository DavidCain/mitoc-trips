from django.test import TestCase
from ws import models


class AuthTests(TestCase):
    fixtures = ['ws']

    def test_equivalence(self):
        """ Dummy test case for getting up and running. """
        self.assertEqual(37, 30 + 7)
