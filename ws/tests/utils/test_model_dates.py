from datetime import date
from unittest.mock import patch

from freezegun import freeze_time

from ws import models
from ws.tests import TestCase, factories
from ws.utils import model_dates as utils


class MissedLectureTests(TestCase):
    """ Test the logic that checks if a participant has missed lectures. """

    def test_legacy_years(self):
        """ Participants are not marked as missing lectures in first years. """
        # We lack records for these early years, so we just assume presence
        participant = models.Participant()
        self.assertFalse(utils.missed_lectures(participant, 2014))
        self.assertFalse(utils.missed_lectures(participant, 2015))

    @freeze_time("Thursday, Jan 4 2018 15:00:00 EST")
    def test_lectures_incomplete(self):
        """ If this year's lectures haven't completed, nobody can be absent. """
        participant = models.Participant()
        with patch.object(utils, 'ws_lectures_complete') as lectures_complete:
            lectures_complete.return_value = False
            self.assertFalse(utils.missed_lectures(participant, 2018))

    @freeze_time("Thursday, Jan 19 2018 15:00:00 EST")
    def test_current_year(self):
        """ Check attendance in current year, after lectures complete.

        We're in a year where attendance is recorded, and we're asking about the current
        year. Did the participant attend?
        """
        par = factories.ParticipantFactory()
        models.LectureAttendance(year=2017, participant=par, creator=par).save()

        # Participant has no attendance recorded for 2018!
        with patch.object(utils, 'ws_lectures_complete') as lectures_complete:
            # If lectures are not yet complete, we don't regard them as missing
            lectures_complete.return_value = False
            self.assertFalse(utils.missed_lectures(par, 2018))

            # If lectures are complete, they're counted as missing
            lectures_complete.return_value = True
            self.assertTrue(utils.missed_lectures(par, 2018))

        # When the participant attended, they did not miss lectures
        models.LectureAttendance(year=2018, participant=par, creator=par).save()
        with patch.object(utils, 'ws_lectures_complete') as lectures_complete:
            lectures_complete.return_value = True
            self.assertFalse(utils.missed_lectures(par, 2018))


class LecturesCompleteTests(TestCase):
    """ Test the method that tries to infer when lectures are over. """

    @staticmethod
    def _create_ws_trip(trip_date, **kwargs):
        factories.TripFactory.create(
            trip_date=trip_date, activity='winter_school', **kwargs
        )

    @freeze_time("Wednesday, Jan 3 2018 15:00:00 EST")
    def test_no_trips_yet(self):
        """ When there are no trips this Winter School, lectures aren't complete.

        (The first trips are posted on Thursday of the first lecture week - without
        these trips, we can reasonably infer that lectures are still ongoing)
        """
        # Create trips from previous Winter School
        self._create_ws_trip(date(2017, 1, 15))
        self._create_ws_trip(date(2017, 1, 28))

        self.assertFalse(utils.ws_lectures_complete())

    @freeze_time("Friday, Jan 13 2017 12:34:00 EST")
    def test_past_trips(self):
        """ When trips have already completed, lectures are definitely over. """
        self._create_ws_trip(date(2017, 1, 12))
        self.assertTrue(utils.ws_lectures_complete())

    def test_future_trips(self):
        """ When there are no past trips, but there are upcoming trips. """

        self._create_ws_trip(date(2018, 1, 5))
        self._create_ws_trip(date(2018, 1, 6))

        # Test calling this function at various times of day
        expectations = {
            # There are future trips, but it's not yet Thursday night
            # (Explanation: Some leaders got ansty and created trips early)
            'Wed 2018-01-03 12:00 EST': False,
            # It's evening, but lectures have just started
            'Thu 2018-01-04 19:00 EST': False,
            # Leaders created trips, and it's after 9 pm, so we infer lectures are over
            'Thu 2018-01-04 21:15 EST': True,
            # It's Friday, with upcoming trips. Lectures are definitely over.
            'Fri 2018-01-05 10:23 EST': True,
        }

        for time_string, lectures_over in expectations.items():
            with freeze_time(time_string):
                self.assertEqual(utils.ws_lectures_complete(), lectures_over)
