"""
Settings for deploying project on Scripts.

Sensitive information (secret key) is left to be filled out.
"""

import os

BASE_NAME = 'ws'  # (part of URL that comes after mitoc.scripts.mit.edu/)
                  # Omit the leading slash (should be a relative URL)
URL_ROOT = os.path.join('/', BASE_NAME)

SECRET_KEY = None

DEBUG = False
TEMPLATE_DEBUG = False
ALLOWED_HOSTS = ['.scripts.mit.edu']


# auth and allauth settings
LOGIN_URL = os.path.join(URL_ROOT, 'accounts/login')
LOGIN_REDIRECT_URL = URL_ROOT
ACCOUNT_LOGOUT_REDIRECT_URL = URL_ROOT
LOGOUT_URL = URL_ROOT

DATABASES = {
     'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'djcain+ws',
        'OPTIONS': {
            'read_default_file': os.path.expanduser('~/.my.cnf'),
        }
    }
}

STATIC_URL = os.path.join(URL_ROOT, 'static/')
STATIC_ROOT = os.path.join('/mit/mitoc/web_scripts/', BASE_NAME, 'static')

ADMIN_MEDIA_PREFIX = '/__scripts/django/static/admin/'

# Emails _must_ be verified before sign-in allowed
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
