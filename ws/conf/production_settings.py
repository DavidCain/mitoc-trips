"""Production settings"""

import os

DEBUG = False

# In true production, 'mitoc-trips.mit.edu'
# Running in Vagrant, this is set to 'mitoc-trips.local'
ALLOWED_HOSTS = [os.environ["DJANGO_ALLOWED_HOST"]]

if os.getenv("EC2_IP"):
    ALLOWED_HOSTS.append(os.environ["EC2_IP"])

ADMINS = (("David Cain", "davidjosephcain@gmail.com"),)

ACCOUNT_EMAIL_VERIFICATION = "mandatory"

EMAIL_BACKEND = "django_smtp_ssl.SSLEmailBackend"
EMAIL_HOST = "email-smtp.us-east-1.amazonaws.com"
EMAIL_PORT = 465
EMAIL_HOST_USER = os.environ["SES_USER"]
EMAIL_HOST_PASSWORD = os.environ["SES_PASSWORD"]

CORS_ORIGIN_WHITELIST = ("https://mitoc.mit.edu",)
CORS_ALLOW_METHODS = ("GET",)

# (Django defaults, for now)
# Consider using Argon2 eventually: https://docs.djangoproject.com/en/2.2/topics/auth/passwords/)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
