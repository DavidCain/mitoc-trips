import unittest
from importlib import reload
from typing import Final
from unittest import mock

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from ws import settings

real_import = __import__


# These settings must be present to prevent key errors loading production_settings
MIN_PROD_SETTINGS: Final = {
    "WS_MODE": "deployed",
    "DJANGO_ALLOWED_HOST": "mitoc-trips.mit.edu",
    "SES_USER": "AKIA0000000000000000",
    "SES_PASSWORD": "some-long-random-password",
}


class SettingsTests(unittest.TestCase):
    @staticmethod
    def _reimport_if_needed(name, *args):
        """If attempting to import a conf module, re-import eagerly (but only that module)

        This method is necessary so that we don't accidentally keep conf imports defined
        with values set by previous tests' imports. Additionally, we must spy on
        `import` to determine if a reload is necessary, since each conf settings file
        looks at env vars and can raise exceptions if those env vars are absent.

        For example, if we were  to reload production settings in a test of local configuration,
        it would raise exceptions! This would happen because production requires some
        env vars that would never be set in local development.
        """
        # pylint: disable=import-outside-toplevel
        if "local_settings" in name:
            from ws.conf import local_settings  # noqa: PLC0415

            reload(local_settings)
        elif "production_settings" in name:
            from ws.conf import production_settings  # noqa: PLC0415

            reload(production_settings)

        return real_import(name, *args)

    def _fresh_settings_load(self) -> None:
        """Do a fresh re-import of the settings module!"""
        with mock.patch("builtins.__import__", side_effect=self._reimport_if_needed):
            reload(settings)

    def test_unittests_default_to_test_settings(self):
        """By default, our test runner uses `test_settings`."""
        with mock.patch("builtins.__import__", wraps=real_import) as import_spy:
            reload(settings)

        imported_modules = [call[0][0] for call in import_spy.call_args_list]
        self.assertFalse(settings.DEBUG)
        self.assertIn("conf.test_settings", imported_modules)
        self.assertNotIn("conf.local_settings", imported_modules)
        self.assertNotIn("conf.production_settings", imported_modules)

    def test_local_settings(self) -> None:
        """We can use an env var to import special local dev settings."""
        with mock.patch.dict("os.environ", {"WS_MODE": "local"}):
            self._fresh_settings_load()

        self.assertTrue(settings.DEBUG)  # Not safe in production, helpful locally
        self.assertEqual(settings.ALLOWED_HOSTS, ["*"])  # For ease of development
        self.assertEqual(settings.ACCOUNT_EMAIL_VERIFICATION, "none")
        self.assertEqual(
            settings.EMAIL_BACKEND, "django.core.mail.backends.console.EmailBackend"
        )

    def test_local_development_with_debug_toolbar(self):
        """We configure the debug toolbar if installed."""

        def fake_toolbar(name, *args):
            if name == "debug_toolbar":
                # (This package won't actually be installed in most test builds)
                # It merely needs to 'import' without raising an exception
                return mock.Mock()
            return self._reimport_if_needed(name, *args)

        with mock.patch("builtins.__import__", side_effect=fake_toolbar):
            reload(settings)

        self.assertIn("debug_toolbar", settings.INSTALLED_APPS)
        self.assertIn(
            "debug_toolbar.middleware.DebugToolbarMiddleware", settings.MIDDLEWARE
        )

    def test_local_development_without_debug_toolbar(self):
        """We configure installed applications properly when debug toolbar is absent.

        In most test builds, we won't have `debug_toolbar` installed, but this guarantees
        coverage of behavior when we do not.
        """

        def debug_toolbar_absent(name, *args):
            if name == "debug_toolbar":
                raise ImportError
            return self._reimport_if_needed(name, *args)

        with mock.patch("builtins.__import__", side_effect=debug_toolbar_absent):
            reload(settings)

        self.assertNotIn("debug_toolbar", settings.INSTALLED_APPS)
        self.assertNotIn(
            "debug_toolbar.middleware.DebugToolbarMiddleware", settings.MIDDLEWARE
        )

    def test_production_security(self) -> None:
        """Sanity check that some key values are set properly in production."""
        with mock.patch.dict("os.environ", MIN_PROD_SETTINGS):
            self._fresh_settings_load()

        self.assertFalse(settings.DEBUG)  # Not safe in production!
        self.assertNotIn(
            "django.contrib.auth.hashers.MD5PasswordHasher", settings.PASSWORD_HASHERS
        )

    def test_sentry_not_initialized_if_envvar_present(self) -> None:
        """During local development, we can disable Sentry."""
        with mock.patch.dict("os.environ", {"SENTRY_DSN": ""}):
            with mock.patch.object(sentry_sdk, "init") as init_sentry:
                self._fresh_settings_load()
        init_sentry.assert_not_called()

    def test_sentry_initialized_from_envvar(self):
        """The DSN for Sentry comes from config."""
        fake_dsn = "https://hex-code@sentry.io/123446"

        with mock.patch.dict("os.environ", {"SENTRY_DSN": fake_dsn}):
            with mock.patch.object(sentry_sdk, "init") as init_sentry:
                self._fresh_settings_load()
        init_sentry.assert_called_once_with(
            fake_dsn,
            integrations=[mock.ANY, mock.ANY],  # Django & Celery, checked separately
            send_default_pii=True,
        )
        integrations = init_sentry.call_args_list[0][1]["integrations"]

        self.assertTrue(isinstance(integrations[0], DjangoIntegration))
        self.assertTrue(isinstance(integrations[1], CeleryIntegration))
