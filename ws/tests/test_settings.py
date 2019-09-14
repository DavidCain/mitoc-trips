import unittest
from importlib import reload
from unittest import mock

from ws import settings

real_import = __import__


class SettingsTests(unittest.TestCase):
    @staticmethod
    def _reimport_if_needed(name, *args):
        """ If attempting to import a conf module, re-import eagerly (but only that module)

        This method is necessary so that we don't accidentally keep conf imports defined
        with values set by previous tests' imports. Additionally, we must spy on
        `import` to determine if a reload is necessary, since each conf settings file
        looks at env vars and can raise exceptions if those env vars are absent.

        For example, if we were  to reload production settings in a test of local configuration,
        it would raise exceptions! This would happen because production requires some
        env vars that would never be set in local development.
        """
        if 'local_settings' in name:
            from ws.conf import local_settings

            reload(local_settings)
        elif 'production_settings' in name:
            from ws.conf import production_settings

            reload(production_settings)

        return real_import(name, *args)

    def _fresh_settings_load(self):
        """ Do a fresh re-import of the settings module! """

        with mock.patch('builtins.__import__', side_effect=self._reimport_if_needed):
            reload(settings)

    def test_unittests_default_to_test_settings(self):
        """ By default, our test runner uses `test_settings`. """
        with mock.patch('builtins.__import__', wraps=real_import) as import_spy:
            reload(settings)

        imported_modules = [call[0][0] for call in import_spy.call_args_list]
        self.assertFalse(settings.DEBUG)
        self.assertIn('conf.test_settings', imported_modules)
        self.assertNotIn('conf.local_settings', imported_modules)
        self.assertNotIn('conf.production_settings', imported_modules)

    def test_local_settings(self):
        """ We can use an env var to import special local dev settings. """
        with mock.patch.dict('os.environ', {'WS_DJANGO_LOCAL': '1'}, clear=True):
            self._fresh_settings_load()

        self.assertTrue(settings.DEBUG)  # Not safe in production, helpful locally
        self.assertEqual(settings.ALLOWED_HOSTS, ['*'])  # For ease of development
        self.assertEqual(settings.ACCOUNT_EMAIL_VERIFICATION, 'none')
        self.assertEqual(
            settings.EMAIL_BACKEND, 'django.core.mail.backends.console.EmailBackend'
        )

    def test_production_settings_with_ec2_ip(self):
        """ By default, we load production settings. """
        env_vars = {
            'EC2_IP': '10.1.2.3',  # (will actually be a public IP)
            'DJANGO_ALLOWED_HOST': 'mitoc-trips.mit.edu',
            'SES_USER': 'AKIA0000000000000000',
            'SES_PASSWORD': 'some-long-random-password',
        }

        with mock.patch.dict('os.environ', env_vars, clear=True):
            self._fresh_settings_load()

        self.assertFalse(settings.DEBUG)  # Not safe in production!
        self.assertEqual(settings.ALLOWED_HOSTS, ['mitoc-trips.mit.edu', '10.1.2.3'])
        self.assertEqual(settings.CORS_ORIGIN_WHITELIST, ('https://mitoc.mit.edu',))

    def test_local_development_with_debug_toolbar(self):
        """ We configure the debug toolbar if installed. """

        def fake_toolbar(name, *args):
            if name == 'debug_toolbar':
                # (This package won't actually be installed in most test builds)
                # It merely needs to 'import' without raising an exception
                return mock.Mock()
            return self._reimport_if_needed(name, *args)

        with mock.patch('builtins.__import__', side_effect=fake_toolbar):
            reload(settings)

        self.assertIn('debug_toolbar', settings.INSTALLED_APPS)
        self.assertIn(
            'debug_toolbar.middleware.DebugToolbarMiddleware', settings.MIDDLEWARE
        )

    def test_local_development_without_debug_toolbar(self):
        """ We configure installed applications properly when debug toolbar is absent.


        In most test builds, we won't have `debug_toolbar` installed, but this guarantees
        coverage of behavior when we do not.
        """

        def debug_toolbar_absent(name, *args):
            if name == 'debug_toolbar':
                raise ImportError
            return self._reimport_if_needed(name, *args)

        with mock.patch('builtins.__import__', side_effect=debug_toolbar_absent):
            reload(settings)

        self.assertNotIn('debug_toolbar', settings.INSTALLED_APPS)
        self.assertNotIn(
            'debug_toolbar.middleware.DebugToolbarMiddleware', settings.MIDDLEWARE
        )

    def test_production_settings_without_ec2_ip(self):
        """ We need not set an EC2_IP (especially if not actually running in AWS) """
        env_vars = {
            'DJANGO_ALLOWED_HOST': 'mitoc-trips.mit.edu',
            'SES_USER': 'AKIA0000000000000000',
            'SES_PASSWORD': 'some-long-random-password',
        }

        with mock.patch.dict('os.environ', env_vars, clear=True):
            self._fresh_settings_load()

        self.assertFalse(settings.DEBUG)  # Not safe in production!
        self.assertEqual(settings.ALLOWED_HOSTS, ['mitoc-trips.mit.edu'])
        self.assertEqual(settings.CORS_ORIGIN_WHITELIST, ('https://mitoc.mit.edu',))
