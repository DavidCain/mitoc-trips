from unittest.mock import patch

from django.test import SimpleTestCase

from ws import models
from ws.lottery import run


class SingleTripLotteryTests(SimpleTestCase):
    @patch.object(models.Trip, 'save')
    def test_fcfs_not_run(self, save_trip):
        """ If a trip's algorithm is not 'lottery', nothing happens. """
        trip = models.Trip(algorithm='fcfs')
        runner = run.SingleTripLotteryRunner(trip)

        trip.algorithm = 'fcfs'
        runner()  # Early exits because it's not a lottery trip
        save_trip.assert_not_called()
