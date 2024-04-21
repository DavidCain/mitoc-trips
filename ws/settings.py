"""Django settings for ws project.

For more information on this file, see
https://docs.djangoproject.com/en/3.2/topics/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
from typing import Any

import sentry_sdk
from celery.schedules import crontab
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

# Configure Sentry right away so that any other errors are captured!
# TODO: Rename env var - Raven was the name of the legacy client
if "RAVEN_DSN" in os.environ:
    # See: https://docs.sentry.io/platforms/python/django/
    sentry_sdk.init(  # pylint: disable=abstract-class-instantiated
        os.environ["RAVEN_DSN"],
        integrations=[DjangoIntegration(), CeleryIntegration()],
        # This attaches basic user data to the event
        send_default_pii=True,
    )

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY", "*this-is-obviously-not-secure-only-use-it-locally*"
)
UNSUBSCRIBE_SECRET_KEY = os.getenv(
    "UNSUBSCRIBE_SECRET_KEY", "*secret-used-only-for-unsubscribe-tokens*"
)
# This secret is used as part of a complete seed for a pseudo-random number generator
# Since random.random is not suitable for cryptographic applications, we use
# a separate secret key rather than re-use SECRET_KEY
PRNG_SEED_SECRET = os.getenv("PRNG_SEED_SECRET", "some-key-unknown-to-participants")

MEMBERSHIP_SECRET_KEY = os.getenv(
    "MEMBERSHIP_SECRET_KEY", "secret shared with the mitoc-aws repo"
)
GEARDB_SECRET_KEY = os.getenv(
    "GEARDB_SECRET_KEY", "secret shared with the mitoc-gear repo"
)
WS_LOTTERY_LOG_DIR = os.getenv("WS_LOTTERY_LOG_DIR", "/tmp/")  # noqa: S108

# URL to an avatar image that is self-hosted
# (Users who opt out of Gravatar would prefer to not have requests made to
#  Gravatar to fetch the "mystery man" image)
PRIVACY_AVATAR_URL = os.getenv(
    "PRIVACY_AVATAR_URL", "https://s3.amazonaws.com/mitoc-trips/privacy/avatar.svg"
)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECT_ROOT = os.path.normpath(os.path.dirname(__file__))

NODE_MODULES = os.path.join(BASE_DIR, "node_modules")

# Settings may override these defaults (easily defined here due to BASE_DIR)
STATIC_URL = "/static/"
STATIC_ROOT = os.getenv("STATIC_ROOT", os.path.join(BASE_DIR, "static"))

STORAGE = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "ws.storage.ManifestStorage",
    },
}

STATICFILES_DIRS = [
    # For the legacy frontend, just put all the files directly in static root
    NODE_MODULES,
    # For the new frontend, collect just the distributed files
    ("frontend", os.path.join(BASE_DIR, "frontend", "dist")),
]

STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "pipeline.finders.ManifestFinder",
)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "pwned_passwords_django.validators.PwnedPasswordsValidator"}
]

LOGIN_REDIRECT_URL = "/"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "phonenumber_field",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "crispy_forms",
    "pipeline",
    "ws.apps.TripsConfig",
    "corsheaders",
    "webpack_loader",
]
try:
    # The debug toolbar is always absent in prod, but optional for local development!
    import debug_toolbar  # pylint: disable=unused-import  # noqa: F401
except ImportError:
    pass
else:
    INSTALLED_APPS.append("debug_toolbar")


# Celery settings
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@127.0.0.1//")
CELERY_RESULT_BACKEND = "rpc"
CELERY_RESULT_PERSISTENT = True  # Don't reset msgs after broker restart (requires RPC)
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

# Try to schedule tasks three times.
# - First retry: immediate
# - Second retry: half a second later
#
# This prevents tasks from hanging forever when the broker is down.
CELERY_BROKER_TRANSPORT_OPTIONS: dict[str, Any] = {
    "max_retries": 2,
    "interval_start": 0,
    "interval_step": 0.5,
    "interval_max": 1,
}

CELERY_BEAT_SCHEDULE = {
    "purge-non-student-discounts": {
        "task": "ws.tasks.purge_non_student_discounts",
        "schedule": crontab(minute=0, hour=2, day_of_week=1),
    },
    "purge-old-medical-data": {
        "task": "ws.tasks.purge_old_medical_data",
        "schedule": crontab(minute=0, hour=2, day_of_week=2),
    },
    "refresh-all-discount-spreadsheets": {
        "task": "ws.tasks.update_all_discount_sheets",
        "schedule": crontab(minute=0, hour=3),
    },
    "send-trip-summaries-email": {
        "task": "ws.tasks.send_trip_summaries_email",
        # Tuesdays around noon (ignore DST)
        "schedule": crontab(minute=0, hour=17, day_of_week=2),
    },
    "remind-participants-to-renew": {
        "task": "ws.tasks.remind_participants_to_renew",
        # Every day at 5pm EST (ignore DST)
        "schedule": crontab(minute=0, hour=22),
    },
    "send-sole-itineraries": {
        "task": "ws.tasks.send_sole_itineraries",
        "schedule": crontab(minute=0, hour=4),
    },
    "run-ws-lottery": {
        "task": "ws.tasks.run_ws_lottery",
        "schedule": crontab(minute=0, hour=14, month_of_year=[1, 2], day_of_week=3),
    },
}

CELERY_TIMEZONE = "UTC"

CRISPY_TEMPLATE_PACK = "bootstrap3"

# A list of known "bad" passwords for which we don't want to hit the HIBP API.
# This will *never* be honored in production -- it's just a local testing tool.
# (Used to test with garbage passwords, avoiding the "change your password!" flow)
ALLOWED_BAD_PASSWORDS: tuple[str, ...] = ()

# It's expected that the settings module define this directly.
# Still, to minimize reliance on wildcard imports, default to off.
DEBUG = False

if os.environ.get("WS_DJANGO_TEST"):
    from .conf.test_settings import *  # pylint: disable=wildcard-import,unused-wildcard-import  # noqa: F403
elif os.environ.get("WS_DJANGO_LOCAL"):
    from .conf.local_settings import *  # pylint: disable=wildcard-import,unused-wildcard-import  # noqa: F403
else:
    from .conf.production_settings import *  # pylint: disable=wildcard-import,unused-wildcard-import  # noqa: F403

# 32 bit signed integers (default before Django 3.2) are plenty big enough for our purposes.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# If working locally, quick start commands:
# CREATE USER ws WITH PASSWORD 'password';
# CREATE DATABASE ws;
# GRANT ALL PRIVILEGES ON DATABASE ws TO ws;
# ALTER USER ws CREATEDB;

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME", "ws"),
        "USER": os.getenv("DATABASE_USER", "ws"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD", "password"),
        "HOST": os.getenv("DATABASE_HOST", "localhost"),
        "PORT": os.getenv("DATABASE_PORT", "5432"),
    },
}


MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.common.CommonMiddleware",
    "ws.middleware.PrefetchGroupsMiddleware",
    "ws.middleware.ParticipantMiddleware",
    "ws.middleware.CustomMessagesMiddleware",
]
if "debug_toolbar" in INSTALLED_APPS:
    MIDDLEWARE.append("debug_toolbar.middleware.DebugToolbarMiddleware")

AUTHENTICATION_BACKENDS = (
    # Needed to login by username in Django admin, regardless of `allauth`
    "django.contrib.auth.backends.ModelBackend",
    # `allauth` specific authentication methods, such as login by e-mail
    "allauth.account.auth_backends.AuthenticationBackend",
)

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(PROJECT_ROOT, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "ws.context_processors.participant_and_groups",
                "ws.context_processors.angular_templates",
            ],
            "debug": DEBUG,
        },
    }
]

SITE_ID = 1

# Log in with only email
ACCOUNT_AUTHENTICATION_METHOD = "email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False

# Just click the link to verify
ACCOUNT_CONFIRM_EMAIL_ON_GET = True

# Always "remember me"
ACCOUNT_SESSION_REMEMBER = True

SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = "ws.social.TrustGoogleEmailOwnershipAdapter"

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": "105568993872-llfunbenb7fndfl17b7bk4mv7uq1jgd5.apps.googleusercontent.com",
            "secret": os.environ.get("GOOGLE_OAUTH_SECRET_KEY", ""),
            "key": "",
        },
        "SCOPE": ["email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}

BURSAR_NAME = os.getenv("BURSAR_NAME", "MITOC Bursar")

ROOT_URLCONF = "ws.urls"

WSGI_APPLICATION = "ws.wsgi.application"


# DocuSign
DOCUSIGN_API_BASE = os.getenv(
    "DOCUSIGN_API_BASE", "https://demo.docusign.net/restapi/v2/"
)
DOCUSIGN_USERNAME = os.getenv("DOCUSIGN_USERNAME", "djcain@mit.edu")
DOCUSIGN_PASSWORD = os.getenv("DOCUSIGN_PASSWORD", "super-secret")
DOCUSIGN_INTEGRATOR_KEY = os.getenv("DOCUSIGN_INTEGRATOR_KEY", "secret-uuid")
DOCUSIGN_WAIVER_TEMPLATE_ID = os.getenv("DOCUSIGN_WAIVER_TEMPLATE_ID", "template-uuid")

# Hit endpoints when we successfully complete a waiver
DOCUSIGN_EVENT_NOTIFICATION = {
    "url": "https://docusign.mitoc.org/members/waiver",
    "loggingEnabled": "true",
    "requireAcknowledgment": "true",
    "useSoapInterface": "false",
    "includeCertificateWithSoap": "false",
    "signMessageWithX509Cert": "true",
    "includeDocuments": "false",  # No need
    "includeCertificateOfCompletion": "false",
    "includeEnvelopeVoidReason": "true",
    "includeTimeZone": "true",  # Timestamps aren't in UTC... >:(
    "includeSenderAccountAsCustomField": "true",
    "includeDocumentFields": "true",
    "envelopeEvents": [{"envelopeEventStatusCode": "completed"}],
    "recipientEvents": [{"recipientEventStatusCode": "Completed"}],
}

# Google Sheet (discount roster) settings
OAUTH_JSON_CREDENTIALS = os.getenv("OAUTH_JSON_CREDENTIALS")
DISABLE_GSHEETS = bool(os.getenv("DISABLE_GSHEETS"))

# Internationalization
# https://docs.djangoproject.com/en/2.2/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/New_York"
USE_I18N = True
USE_TZ = True

# Participants must update their profile information every ~6 months
MUST_UPDATE_AFTER_DAYS = 180

vendor_js = [
    # (jQuery is required by many legacy deps, but is loaded with Bootstrap 3)
    # 'jquery/dist/jquery.min.js'
    "angular/angular.js",
    "lodash/lodash.js",
    "footable/js/footable.js",
    "footable/js/footable.sort.js",
    "jquery-ui/ui/core.js",
    "jquery-ui/ui/widget.js",
    "jquery-ui/ui/mouse.js",
    "jquery-ui/ui/sortable.js",
    "jquery-ui/jquery-ui.js",
    "jquery-ui-touch-punch/jquery.ui.touch-punch.js",
    "ui-select/dist/select.js",
    "angular-sanitize/angular-sanitize.js",
    "angular-ui-sortable/dist/sortable.js",
    "js/ui-bootstrap-tpls-0.14.3.js",
    # Libraries to support international phone numbers
    "google-libphonenumber/dist/browser/libphonenumber.js",
    "digits-trie/dist/digits-trie.js",
    "bc-countries/dist/bc-countries.js",
    "bc-phone-number/dist/js/bc-phone-number.js",
]

local_js = ["js/ws/*.js", "js/footable_breakpoints.js"]

PIPELINE = {
    "JS_COMPRESSOR": "pipeline.compressors.uglifyjs.UglifyJSCompressor",
    "CSS_COMPRESSOR": "pipeline.compressors.yuglify.YuglifyCompressor",
    "JAVASCRIPT": {
        # Bootstrap JS is used on most every page (in the main menu)
        # Other JavaScript is in the process of being deprecated, so we should be able to serve just this.
        "bootstrap": {
            "source_filenames": [
                "jquery/dist/jquery.min.js",
                "bootstrap/dist/js/bootstrap.js",
            ],
            "output_filename": "js/bootstrap.js",
            "extra_context": {"defer": True},
        },
        # FontAwesome is served separately to use a data attribute hack
        # It's also served to allow its use on raw HTML pages that ignore legacy JS.
        # (Note that the hack relies on the filename containing 'fontawesome')
        "fontawesome": {
            "source_filenames": ["@fortawesome/fontawesome-free/js/all.js"],
            "output_filename": "js/fontawesome.js",  # WARNING: don't change.
            "extra_context": {"defer": True},
        },
        #
        # ******** WARNING: the below bundles use the legacy JavaScript frontend ******** #
        #
        # Vendor assets change very rarely, we can keep the cache a long time
        "legacy_vendor": {
            "source_filenames": vendor_js,
            "output_filename": "js/vendor.js",
            "extra_context": {"defer": True},
        },
        "legacy_app": {
            "source_filenames": local_js,
            "output_filename": "js/app.js",
            "extra_context": {"defer": True},
        },
    },
    "STYLESHEETS": {
        "app": {
            "source_filenames": [
                "css/layout.css",
                "css/footable.core.css",  # Forked... =(
                "css/footable.standalone.css",
                "bootstrap/dist/css/bootstrap.min.css",
                "ui-select/dist/select.min.css",
                "bc-phone-number/dist/css/bc-phone-number.css",
                # Flags are an optional enhancement to the country picker
                "bc-css-flags/dist/css/bc-css-flags.css",
                # Could be deferred separately, but it's only a few KB
                "@fortawesome/fontawesome-free/css/svg-with-js.css",
            ],
            "output_filename": "css/app.css",
        }
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {module} {message}", "style": "{"},
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": os.getenv("DJANGO_LOG_FILE", "/tmp/django.log"),  # noqa: S108
            "formatter": "verbose",
        }
    },
    "loggers": {
        "django": {"handlers": ["file"], "level": "ERROR", "propagate": True},
        "ws": {"handlers": ["file"], "level": "INFO", "propagate": True},
    },
}

FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
WEBPACK_LOADER = {
    "DEFAULT": {
        "CACHE": DEBUG,
        "BUNDLE_DIR_NAME": "/static/frontend/",
        "STATS_FILE": os.path.join(FRONTEND_DIR, "webpack-stats.json"),
    }
}
