""" Production settings """

import os


DEBUG = False
TEMPLATE_DEBUG = False
ALLOWED_HOSTS = ['trips.mitoc.org', 'mitoc-trips.mit.edu']
if os.getenv('EC2_IP'):
    ALLOWED_HOSTS.append(os.environ['EC2_IP'])

ADMINS = (('David Cain', 'davidjosephcain@gmail.com'),)

SERVER_EMAIL = 'no-reply@mitoc.org'
DEFAULT_FROM_EMAIL = 'mitoc-trips@mit.edu'

ACCOUNT_EMAIL_VERIFICATION = 'mandatory'

EMAIL_BACKEND = 'django_smtp_ssl.SSLEmailBackend'
EMAIL_HOST = 'email-smtp.us-east-1.amazonaws.com'
EMAIL_PORT = 465
EMAIL_HOST_USER = os.getenv('SES_USER')
EMAIL_HOST_PASSWORD = os.getenv('SES_PASSWORD')

# Includes production TripsConfig and omits debug toolbar
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
    'raven.contrib.django.raven_compat',
    'ws.apps.TripsConfig',
    'corsheaders',
)

CORS_ORIGIN_WHITELIST = ('mitoc.mit.edu')
CORS_ALLOW_METHODS = ('GET')
