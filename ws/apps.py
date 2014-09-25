from django.apps import AppConfig
from django.contrib.auth.models import Group
from django.db.utils import OperationalError, ProgrammingError


class WinterSchoolConfig(AppConfig):
    name = 'ws'
    verbose_name = "Winter School Signup"

    def load_signals(self):
        try:
            import signals
        except:
            print "Failed to load signals"  # Database initialization, etc.
        else:
            print "Loaded signals"

    def create_groups(self):
        # Groups don't need Django permissions defined.
        # Their ability to modify models is controlled by access to views
        try:
            Group.objects.get_or_create(name='leaders')
            Group.objects.get_or_create(name='users_with_info')
            Group.objects.get_or_create(name='WSC')
        except (OperationalError, ProgrammingError):
            print "Can't create groups"
            print "Django tables likely not created yet (run migrate)."
        else:
            print "Groups initialized"  # May have already been there

    def ready(self):
        self.load_signals()
        self.create_groups()
