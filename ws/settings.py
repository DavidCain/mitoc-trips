"""
Django settings for ws project.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os

from celery.schedules import crontab
import raven


SECRET_KEY = os.getenv('DJANGO_SECRET_KEY',
                       '*this-is-obviously-not-secure-only-use-it-locally*')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_ROOT = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))

BOWER_COMPONENTS = os.path.join(BASE_DIR, 'bower_components')

# Settings may override these defaults (easily defined here due to BASE_DIR)
STATIC_URL = '/static/'
STATIC_ROOT = os.getenv('STATIC_ROOT', os.path.join(BASE_DIR, 'static'))

STATICFILES_STORAGE = 'ws.storage.CachedStorage'

STATICFILES_DIRS = [
    BOWER_COMPONENTS
]

STATICFILES_FINDERS = (
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
    'pipeline.finders.PipelineFinder',
)

# auth and allauth settings
LOGIN_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/'

if os.environ.get('WS_TEST_CONFIG'):
    from .conf.test_settings import *
elif os.environ.get('WS_DJANGO_LOCAL'):
    from .conf.local_settings import *
else:
    from .conf.production_settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': os.getenv('DATABASE_NAME', 'ws'),
        'USER': os.getenv('DATABASE_USER', 'ws'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD', 'password'),
        'HOST': os.getenv('DATABASE_HOST', 'localhost'),
        'PORT': os.getenv('DATABASE_PORT', '5432'),
    },
    'auth_db': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': os.getenv('AUTH_DATABASE_NAME', 'auth_db'),
        'USER': os.getenv('DATABASE_USER', 'ws'),
        'PASSWORD': os.getenv('DATABASE_PASSWORD', 'password'),
        'HOST': os.getenv('DATABASE_HOST', 'localhost'),
        'PORT': os.getenv('DATABASE_PORT', '5432'),
    },
    'geardb': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('GEAR_DATABASE_NAME', 'geardb'),
        'USER': os.getenv('GEAR_DATABASE_USER', 'ws'),
        'PASSWORD': os.getenv('GEAR_DATABASE_PASSWORD', 'password'),
        'HOST': os.getenv('GEAR_DATABASE_HOST', 'localhost'),
        'PORT': os.getenv('GEAR_DATABASE_PORT', '3306'),
    },
}
DATABASE_ROUTERS = ['ws.routers.AuthRouter']

MIDDLEWARE_CLASSES = [
    'django.middleware.gzip.GZipMiddleware',
    'pipeline.middleware.MinifyHTMLMiddleware',
    'djng.middleware.AngularUrlMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'ws.middleware.PrefetchGroupsMiddleware',
    'ws.middleware.ParticipantMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
if 'debug_toolbar' in INSTALLED_APPS:
    MIDDLEWARE_CLASSES.append('debug_toolbar.middleware.DebugToolbarMiddleware')
if 'corsheaders' in INSTALLED_APPS:
    MIDDLEWARE_CLASSES.insert(0, 'corsheaders.middleware.CorsMiddleware')
    MIDDLEWARE_CLASSES.append('django.middleware.common.CommonMiddleware')

AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",
    # `allauth` specific authentication methods, such as login by e-mail
    "allauth.account.auth_backends.AuthenticationBackend"
)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(PROJECT_ROOT, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "ws.context_processors.participant_and_groups",
            ],
        },
    },
]

# auth and allauth settings
SITE_ID = "1"

# Log in with only email
ACCOUNT_AUTHENTICATION_METHOD = 'email'
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False

# Just click the link to verify
ACCOUNT_CONFIRM_EMAIL_ON_GET = True

# Always "remember me"
ACCOUNT_SESSION_REMEMBER = True

ROOT_URLCONF = 'ws.urls'

WSGI_APPLICATION = 'ws.wsgi.application'


# Celery settings

BROKER_URL = os.getenv('BROKER_URL', 'amqp://guest:guest@127.0.0.1//')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'amqp')
CELERY_TASK_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

CELERYBEAT_SCHEDULE = {
    'purge-non-student-discounts': {
        'task': 'ws.tasks.purge_non_student_discounts',
        'schedule': crontab(minute=0, hour=2, day_of_week=1)
    },
    'refresh-all-discount-spreadsheets': {
        'task': 'ws.tasks.update_all_discount_sheets',
        'schedule': crontab(minute=0, hour=3)
    },
    #'run-ws-lottery': {
    #    'task': 'ws.tasks.run_ws_lottery',
    #    'schedule': crontab(minute=0, hour=11)
    #},
}

CELERY_TIMEZONE = 'UTC'

# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/New_York'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Project-specific settings
MUST_UPDATE_AFTER_DAYS = 180

# Break packages up based on how they'll be served

# CDN libraries are for basic, commonplace libraries (and are loaded first)
cdn_libs = ['jquery/dist/jquery.min.js', 'angular/angular.js', 'd3/d3.min.js']


other_libs = ['lodash/dist/lodash.js',
              'bootstrap/dist/js/bootstrap.min.js',
              'footable/js/footable.js',
              'footable/js/footable.sort.js',
              'jquery-ui/ui/core.js',
              'jquery-ui/ui/widget.js',
              'jquery-ui/ui/mouse.js',
              'jquery-ui/ui/sortable.js',
              'jquery-ui/jquery-ui.js',
              'jqueryui-touch-punch/jquery.ui.touch-punch.js',
              'djng/js/django-angular.js',
              'angular-ui-select/dist/select.js',
              'angular-gravatar/build/angular-gravatar.min.js',
              'angular-sanitize/angular-sanitize.js',
              'angular-ui-sortable/sortable.js',
              'js/ui-bootstrap-tpls-0.14.3.js',
              ]

local_js = ['js/ws/*.js', 'js/footable_breakpoints.js']

PIPELINE = {
    'JS_COMPRESSOR': 'pipeline.compressors.uglifyjs.UglifyJSCompressor',
    'CSS_COMPRESSOR': 'pipeline.compressors.yuglify.YuglifyCompressor',
    'JAVASCRIPT': {
        # With jQuery and Angular served via CDN, this is everything
        'app': {
            'source_filenames': other_libs + local_js,
            'output_filename': 'js/app.js',
        },
        # Must be served before the application (to catch any errors)
        'raven': {
            'source_filenames': [
                'raven-js/dist/raven.min.js',
                'angular-raven/angular-raven.min.js',
            ],
            'output_filename': 'js/raven.js',
        },
    },
    'STYLESHEETS': {
        'app': {
            'source_filenames': (
                'css/layout.css',
                'css/footable.core.css',  # Forked... =(
                'css/footable.standalone.css',
                'bootstrap/dist/css/bootstrap.min.css',
                'angular-ui-select/dist/select.min.css',
                'font-awesome/css/font-awesome.min.css',
            ),
            'output_filename': 'css/app.css',
        }
    },
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.getenv('DJANGO_ERROR_FILE', '/tmp/django_errors.log'),
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
    },
}


RAVEN_CONFIG = {
    'dsn': os.getenv('RAVEN_DSN'),  # If absent, nothing happens
    'release': raven.fetch_git_sha(BASE_DIR),
}
