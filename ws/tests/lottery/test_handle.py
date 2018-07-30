from django.test import SimpleTestCase

from ws.lottery import handle
from ws import models


class DriverTests(SimpleTestCase):
    def test_no_lotteryinfo(self):
        """ Don't regard anybody as a driver if they didn't submit prefs. """
        par = models.Participant()
        self.assertFalse(handle.par_is_driver(par))

    def test_lotteryinfo(self):
        """ Drivers are based off car status from that week. """
        par = models.Participant()
        par.lotteryinfo = models.LotteryInfo(car_status=None)
        self.assertFalse(handle.par_is_driver(par))

        par.lotteryinfo = models.LotteryInfo(car_status='own')
        self.assertTrue(handle.par_is_driver(par))
        par.lotteryinfo = models.LotteryInfo(car_status='rent')
        self.assertTrue(handle.par_is_driver(par))
