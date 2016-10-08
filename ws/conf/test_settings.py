"""
Test settings!
  - Send emails to console
"""

DEBUG = True
ALLOWED_HOSTS = []

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Don't send emails to verify email addresses (rapid account creation)
#ACCOUNT_EMAIL_VERIFICATION = 'none'


INSTALLED_APPS = (
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'localflavor',
    'allauth',
    'allauth.account',
    'djng',
    'pipeline',
    'raven.contrib.django.raven_compat',
    'ws.apps.TestConfig',
)
