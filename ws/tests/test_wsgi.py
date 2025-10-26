import os
import unittest
from unittest import mock

from django import core


class WsgiTest(unittest.TestCase):
    def test_exposes_application_in_var(self) -> None:
        """The WSGI script expects an application available."""
        with mock.patch.object(
            core.wsgi, "get_wsgi_application", wraps=core.wsgi.get_wsgi_application
        ) as get_app:
            from ws import (  # pylint: disable=import-outside-toplevel  # noqa: PLC0415
                wsgi,
            )

        get_app.assert_called_once()
        self.assertTrue(isinstance(wsgi.application, core.handlers.wsgi.WSGIHandler))

        # We also set the Django settings module correctly
        self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], "ws.settings")
