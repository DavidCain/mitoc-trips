from django.db import connections
from django.test import SimpleTestCase


class ConnectionTests(SimpleTestCase):
    def test_transaction_support(self):
        """ Ensure that all connections support transactions.

        Especially within unit tests, we expect support for transactions on all
        databases.
        """
        for conn in connections.all():
            self.assertTrue(conn.features.supports_transactions)
