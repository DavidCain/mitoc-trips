from django.apps import AppConfig


class WinterSchoolConfig(AppConfig):
    name = 'ws'
    verbose_name = "Winter School Signup"

    def ready(self):
        try:
            import signals
        except:
            print "Failed to load signals"  # Database initialization, etc.
        else:
            print "Loaded signals"
