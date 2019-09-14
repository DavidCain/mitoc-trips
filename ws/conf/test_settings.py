""" Test settings

Intended to mirror production as much as is possible.
"""

DEBUG = False

ALLOWED_HOSTS = ['*']

ADMINS = (('David Cain', 'davidjosephcain@gmail.com'),)

SERVER_EMAIL = 'no-reply@mitoc.org'
DEFAULT_FROM_EMAIL = 'mitoc-trips@mit.edu'

ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

CORS_ORIGIN_WHITELIST = ('https://mitoc.mit.edu',)
CORS_ALLOW_METHODS = ('GET',)
