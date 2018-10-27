from django.apps import AppConfig


class TestConfig(AppConfig):
    """ A simple configuration that doesn't load signals. """
    name = 'ws'
    verbose_name = "MITOC Trips"


class TripsConfig(AppConfig):
    name = 'ws'
    verbose_name = "MITOC Trips"

    def load_signals(self):
        from . import signals  # pylint: disable=unused-variable

    def ready(self):
        self.load_signals()
