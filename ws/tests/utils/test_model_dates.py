from datetime import datetime
from unittest.mock import PropertyMock, patch

from django.test import SimpleTestCase

from ws import models
from ws.utils import model_dates as utils


class MissedLectureTests(SimpleTestCase):
    """ Test the logic that checks if a participant has missed lectures. """

    def test_legacy_years(self):
        """ Participants are not marked as missing lectures in first years. """
        # We lack records for these early years, so we just assume presence
        participant = None  # Won't access the object anyway
        self.assertFalse(utils.missed_lectures(participant, 2014))
        self.assertFalse(utils.missed_lectures(participant, 2015))

    @patch('ws.utils.model_dates.ws_lectures_complete')
    @patch('ws.utils.dates.ws_year')
    def test_lectures_incomplete(self, ws_year, ws_lectures_complete):
        """ If this year's lectures haven't completed, nobody can be absent. """
        ws_lectures_complete.return_value = False
        participant = None  # Won't access the object anyway
        ws_year.return_value = current_year = 2525
        self.assertFalse(utils.missed_lectures(participant, current_year))

    @patch('ws.models.Participant.lectureattendance_set', new_callable=PropertyMock)
    @patch('ws.utils.model_dates.ws_lectures_complete')
    @patch('ws.utils.dates.ws_year')
    def test_current_year(self, ws_year, ws_lectures_complete, lecture_attendance):
        """ Check attendance in current year, after lectures complete.

        We're in a year where attendance is recorded, and we're asking about the current
        year. Did the participant attend?
        """
        participant = models.Participant()

        # We're asking about the current WS season, when lectures have occurred
        ws_year.return_value = current_year = 2020
        ws_lectures_complete.return_value = True

        attendance_exists = lecture_attendance.return_value.filter.return_value.exists

        # When participant has no attendance recorded, they've missed lectures
        attendance_exists.return_value = False
        self.assertTrue(utils.missed_lectures(participant, current_year))

        # When the participant attended, they did not miss lectures
        attendance_exists.return_value = True
        self.assertFalse(utils.missed_lectures(participant, current_year))


class LecturesCompleteTests(SimpleTestCase):
    """ Test the method that tries to infer when lectures are over. """

    @patch('ws.utils.model_dates.ws_trips_this_year')
    def test_no_trips_yet(self, ws_trips):
        """ When there are no trips (past or planned), lectures aren't complete.

        (The first trips are posted on Thursday of the first lecture week - without
        these trips, we can reasonably infer that lectures are still ongoing)
        """
        # Any filtering on trips returns an empty list (mocking an empty QuerySet)
        ws_trips.return_value.filter.return_value = []
        self.assertFalse(utils.ws_lectures_complete())

    @patch('ws.utils.model_dates.ws_trips_this_year')
    def test_past_trips(self, ws_trips):
        """ When trips have already completed, lectures are definitely over. """

        def past_only(**kwargs):
            if 'trip_date__lt' in kwargs:
                return [models.Trip(name="Some past trip")]
            else:
                return []

        ws_trips.return_value.filter.side_effect = past_only
        self.assertTrue(utils.ws_lectures_complete())

    @patch('ws.utils.dates.local_now')
    @patch('ws.utils.model_dates.ws_trips_this_year')
    def test_future_trips(self, ws_trips, local_now):
        """ When there are no past trips, but there are upcoming trips. """

        def future_only(**kwargs):
            """ There are no trips in the past, but there are some upcoming. """
            if 'trip_date__lt' in kwargs:
                return []
            elif 'trip_date__gte' in kwargs:
                return [models.Trip(name="Some upcoming trip")]
            return []

        ws_trips.return_value.filter.side_effect = future_only

        # Test calling this function at various times of day
        time_fmt = '%a %Y-%m-%d %H:%M'
        expectations = {
            # There are future trips, but it's not yet Thursday night
            # (Explanation: Some leaders got ansty and created trips early)
            'Wed 2018-01-03 12:00': False,
            # It's evening, but lectures have just started
            'Thu 2018-01-04 19:00': False,
            # Leaders created trips, and it's after 9 pm, so we infer lectures are over
            'Thu 2018-01-04 21:15': True,
            # It's Friday, with upcoming trips. Lectures are definitely over.
            'Fri 2018-01-05 10:23': True,
        }

        for time_string, lectures_over in expectations.items():
            local_now.return_value = datetime.strptime(time_string, time_fmt)
            self.assertEqual(utils.ws_lectures_complete(), lectures_over)
