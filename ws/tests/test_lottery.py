import mock

from ws import lottery
from ws import models

from django.test import SimpleTestCase


class LotteryPairingTests(SimpleTestCase):
    """ Test "pairing" of participants. """
    def test_no_reciprocal_pairing(self):
        """ User has not requested to be paired with anybody. """
        par = models.Participant()  # No LotteryInfo
        self.assertFalse(lottery.reciprocally_paired(par))

        # LotteryInfo exists, but paired participant is None
        par.lotteryinfo = models.LotteryInfo(paired_with=None)
        self.assertFalse(lottery.reciprocally_paired(par))

    def test_unrequited(self):
        """ One half of the pair wants to be paired with the other. """
        stalker = models.Participant()
        target = models.Participant()
        stalker.lotteryinfo = models.LotteryInfo(paired_with=target)

        self.assertFalse(lottery.reciprocally_paired(stalker))
        self.assertFalse(lottery.reciprocally_paired(target))

    def test_reciprocation(self):
        """ Both participants want to be paired with one another. """
        romeo = models.Participant()
        juliet = models.Participant()
        romeo.lotteryinfo = models.LotteryInfo(paired_with=juliet)
        juliet.lotteryinfo = models.LotteryInfo(paired_with=romeo)

        self.assertTrue(lottery.reciprocally_paired(romeo))
        self.assertTrue(lottery.reciprocally_paired(juliet))


class DriverTests(SimpleTestCase):
    def test_no_lotteryinfo(self):
        """ Don't regard anybody as a driver if they didn't submit prefs. """
        par = models.Participant()
        self.assertFalse(lottery.par_is_driver(par))

    def test_lotteryinfo(self):
        """ Drivers are based off car status from that week. """
        par = models.Participant()
        par.lotteryinfo = models.LotteryInfo(car_status=None)
        self.assertFalse(lottery.par_is_driver(par))

        par.lotteryinfo = models.LotteryInfo(car_status='own')
        self.assertTrue(lottery.par_is_driver(par))
        par.lotteryinfo = models.LotteryInfo(car_status='rent')
        self.assertTrue(lottery.par_is_driver(par))


class FlakeFactorTests(SimpleTestCase):
    """ Test the "flake factor" used to identify unreliable participants. """
    def setUp(self):
        self.ranker = lottery.WinterSchoolParticipantRanker()
        self.trip_mapper = {}  # Maps from named trips to trip object & feedback

        trip_names = ['one', 'two', 'three']
        for name in trip_names:
            trip = models.Trip(name=name)
            self.trip_mapper[name] = {
                'trip': trip,
                'feedback': []
            }

    def past_ws_trips(self, participant):
        """ For mocking WinterSchoolParticipantRanker.past_ws_trips. """
        return [val['trip'] for val in self.trip_mapper.values()]

    def get_feedback(self, **kwargs):
        """ Mock participant.feedback_set.filter(trip=trip). """
        trip = kwargs.get('trip')
        feedback_objects = self.trip_mapper[trip.name]['feedback']
        feedback = mock.MagicMock()
        feedback.__iter__.return_value = feedback_objects
        feedback.exists.return_value = len(feedback_objects)
        return feedback

    @mock.patch('ws.models.Participant.feedback_set', new_callable=mock.PropertyMock)
    @mock.patch('ws.lottery.WinterSchoolParticipantRanker.past_ws_trips')
    def test_flake_score(self, past_ws_trips, feedback_set):
        """ Check flake factor scoring participant showed up for all trips. """
        par = models.Participant()

        past_ws_trips.side_effect = self.past_ws_trips
        feedback_set.return_value.filter.side_effect = self.get_feedback

        # Participant has a perfect record of attending each trip
        for name, lookup in self.trip_mapper.items():
            trip = lookup['trip']
            showed_up = models.Feedback(trip=trip, participant=par, showed_up=True)
            lookup['feedback'] = [showed_up]

        # Final score is -2 for each trip
        perfect_score = -2 * len(self.trip_mapper)
        self.assertEqual(self.ranker.get_flake_factor(par), perfect_score)

        # We looked at each of the participant's past trips
        past_ws_trips.assert_called_with(par)

        # If one trip doesn't have feedback, we don't factor that into the score
        for name, lookup in self.trip_mapper.items():
            lookup['feedback'] = []
            break
        self.assertEqual(self.ranker.get_flake_factor(par), perfect_score + 2)

        # If none of the trips have feedback, that's a score of 0
        for name, lookup in self.trip_mapper.items():
            lookup['feedback'] = []
        self.assertEqual(self.ranker.get_flake_factor(par), 0)

        # Each flake is an additional 5 points (trips with no feedback still ignored)
        for i, name in enumerate(self.trip_mapper, start=1):
            flaked = models.Feedback(trip=trip, participant=par, showed_up=False)
            self.trip_mapper[name]['feedback'] = [flaked]
            self.assertEqual(self.ranker.get_flake_factor(par), i * 5)

    @mock.patch('ws.models.Participant.feedback_set', new_callable=mock.PropertyMock)
    @mock.patch('ws.lottery.WinterSchoolParticipantRanker.past_ws_trips')
    def test_disagreement(self, past_ws_trips, feedback_set):
        """ If only one leader reports them as flaking, that's a flake. """
        par = models.Participant()

        past_ws_trips.side_effect = self.past_ws_trips
        feedback_set.return_value.filter.side_effect = self.get_feedback

        # Participant has a perfect record of attending each trip
        for name, lookup in self.trip_mapper.items():
            trip = lookup['trip']
            showed_up = models.Feedback(trip=trip, participant=par, showed_up=True)
            showed_up2 = models.Feedback(trip=trip, participant=par, showed_up=True)
            flaked = models.Feedback(trip=trip, participant=par, showed_up=False)
            lookup['feedback'] = [showed_up, showed_up2, flaked]

        # Each trip counts as 5 points (a flake on each)
        self.assertEqual(self.ranker.get_flake_factor(par), 5 * len(self.trip_mapper))
