from django.apps import AppConfig


class WinterSchoolConfig(AppConfig):
    name = 'ws'
    verbose_name = "Winter School Signup"

    def ready(self):
        import signals
        print "Loaded signals"
