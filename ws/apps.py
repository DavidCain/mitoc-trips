from django.apps import AppConfig


class TestConfig(AppConfig):
    """ A simple configuration that doesn't load signals. """

    name = 'ws'
    verbose_name = "MITOC Trips"


class TripsConfig(AppConfig):
    name = 'ws'
    verbose_name = "MITOC Trips"

    @staticmethod
    def load_signals():
        from . import signals  # pylint: disable=unused-import, unused-variable

    def ready(self):
        self.load_signals()
