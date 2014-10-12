"""
Local settings, intended for use on a local computer for basic
feature testing.

  - Exposed secret key
  - DEBUG enabled
  - Project root is just '/'
  - Send emails to console
"""

import os

SECRET_KEY = '-6xhhnvt=i%tkmiy2#nm@mu^-=%bk-wbe5pu1vrd_gm^6&%v*s'

DEBUG = True
TEMPLATE_DEBUG = True
ALLOWED_HOSTS = []

# auth and allauth settings
LOGIN_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/'

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'db.sqlite3',
    }
}

# Don't send emails to verify email addresses (rapid account creation)
ACCOUNT_EMAIL_VERIFICATION = 'none'
