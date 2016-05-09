""" Production settings """

DEBUG = True  # False
TEMPLATE_DEBUG = True  # False
ALLOWED_HOSTS = []  # ['trips.mitoc.edu']

ADMINS = (('David Cain', 'davidjosephcain@gmail.com'),)

SERVER_EMAIL = 'no-reply@mitoc.org'
DEFAULT_EMAIL_FROM = 'trips@mitoc.org'

ACCOUNT_EMAIL_VERIFICATION = 'none'  # 'mandatory'

# While we configure actual email, this is a useful interim
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = '/webapps/ws/logs/ws_emails.log'
