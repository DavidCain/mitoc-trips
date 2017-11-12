"""
Local settings, intended for use on a local computer for basic
feature testing.

  - Exposed secret key
  - DEBUG enabled
  - Project root is just '/'
  - Send emails to console
"""

DEBUG = True
ALLOWED_HOSTS = []

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Don't send emails to verify email addresses (rapid account creation)
ACCOUNT_EMAIL_VERIFICATION = 'none'


# Includes Debug Toolbar
INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'localflavor',
    'phonenumber_field',
    'allauth',
    'allauth.account',
    'djng',
    'pipeline',
    'debug_toolbar',
    'raven.contrib.django.raven_compat',
    'ws.apps.TripsConfig',
)

DEBUG_TOOLBAR_PATCH_SETTINGS = False
INTERNAL_IPS = ['127.0.0.1', '192.168.33.15']
