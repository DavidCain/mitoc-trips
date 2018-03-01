from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError


class TestConfig(AppConfig):
    """ A simple configuration that doesn't load signals.

    This facilitates saving data from fixtures after the app is ready (since we
    don't want every post_save to trigger a signal).
    """
    name = 'ws'
    verbose_name = "MITOC Trips"


class TripsConfig(AppConfig):
    name = 'ws'
    verbose_name = "MITOC Trips"

    def load_signals(self):
        try:
            from . import signals  # noQA
        except:
            pass  # Database initialization, etc.

    def create_groups(self):
        # Groups don't need Django permissions defined.
        # Their ability to modify models is controlled by access to views
        from django.contrib.auth.models import Group
        try:
            Group.objects.get_or_create(name='leaders')
            Group.objects.get_or_create(name='users_with_info')
            Group.objects.get_or_create(name='WSC')
            Group.objects.get_or_create(name='WIMP')

            # Created based off all activites in LeaderRating.CLOSED_ACTIVITES
            # (with "WSC" being a special case for the time being)
            Group.objects.get_or_create(name='biking_chair')
            Group.objects.get_or_create(name='boating_chair')
            Group.objects.get_or_create(name='cabin_chair')
            Group.objects.get_or_create(name='climbing_chair')
            Group.objects.get_or_create(name='hiking_chair')
        except (OperationalError, ProgrammingError):
            print("Can't create groups")
            print("Django tables likely not created yet (run migrate).")

    def ready(self):
        self.load_signals()
        self.create_groups()
