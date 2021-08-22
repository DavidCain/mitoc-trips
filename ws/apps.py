from django.apps import AppConfig


class TripsConfig(AppConfig):
    name = 'ws'
    verbose_name = "MITOC Trips"

    @staticmethod
    def load_signals():
        # pylint: disable=unused-import, unused-variable, import-outside-toplevel
        from . import signals

    def ready(self):
        self.load_signals()
