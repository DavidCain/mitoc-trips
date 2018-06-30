from unittest.mock import MagicMock, PropertyMock, patch
import itertools

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
        feedback = MagicMock()
        feedback.__iter__.return_value = feedback_objects
        feedback.exists.return_value = len(feedback_objects)
        return feedback

    @patch('ws.models.Participant.feedback_set', new_callable=PropertyMock)
    @patch('ws.lottery.WinterSchoolParticipantRanker.past_ws_trips')
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
        self.assertEqual(self.ranker.flake_factor(par), perfect_score)

        # We looked at each of the participant's past trips
        past_ws_trips.assert_called_with(par)

        # If one trip doesn't have feedback, we don't factor that into the score
        for name, lookup in self.trip_mapper.items():
            lookup['feedback'] = []
            break
        self.assertEqual(self.ranker.flake_factor(par), perfect_score + 2)

        # If none of the trips have feedback, that's a score of 0
        for name, lookup in self.trip_mapper.items():
            lookup['feedback'] = []
        self.assertEqual(self.ranker.flake_factor(par), 0)

        # Each flake is an additional 5 points (trips with no feedback still ignored)
        for i, name in enumerate(self.trip_mapper, start=1):
            flaked = models.Feedback(trip=trip, participant=par, showed_up=False)
            self.trip_mapper[name]['feedback'] = [flaked]
            self.assertEqual(self.ranker.flake_factor(par), i * 5)

    @patch('ws.models.Participant.feedback_set', new_callable=PropertyMock)
    @patch('ws.lottery.WinterSchoolParticipantRanker.past_ws_trips')
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
        self.assertEqual(self.ranker.flake_factor(par), 5 * len(self.trip_mapper))


class ParticipantRankingTests(SimpleTestCase):
    """ Test the logic by which we determine users with "first pick" status. """
    mocked_par_methods = ['number_trips_led', 'number_ws_trips', 'flake_factor']

    def setUp(self):
        base = 'ws.lottery.WinterSchoolParticipantRanker'
        patches = [patch(f'{base}.{name}') for name in self.mocked_par_methods]

        for patched in patches:
            patched.start()
        for patched in reversed(patches):
            self.addCleanup(patched.stop)

        # (Mocked-out methods accessible at self.ranker.<method_name>)
        self.ranker = lottery.WinterSchoolParticipantRanker()

    def expect_ranking(self, *participants):
        """ Any permutation of participant ordering results in the same output. """
        for permutation in itertools.permutations(participants):
            ranked = sorted(permutation, key=self.ranker.priority_key)
            self.assertEqual(list(participants), ranked)

    def test_flaking(self):
        """ Those who flake on trips always come last. """
        # Flaking participant is an MIT undergrad (would normally get priority)
        serial_flaker = models.Participant(affiliation='MU')
        flaked_once = models.Participant(affiliation='MG')
        reliable = models.Participant(affiliation='NA')

        # NOTE: Must use id since these objects have no pk (they're unhashable)
        mocked_counts = {
            id(flaked_once): {
                'number_trips_led': 8,
                'number_ws_trips': 2,
                'flake_factor': 5  # Flaked on one of the two trips
            },
            id(serial_flaker): {
                'number_trips_led': 4,
                'number_ws_trips': 3,
                'flake_factor': 15  # Flaked on all three!
            },
            id(reliable): {
                'number_trips_led': 0,
                'number_ws_trips': 4,
                'flake_factor': -8  # Showed up for all four trips
            },
        }

        for attr in self.mocked_par_methods:
            method = getattr(self.ranker, attr)
            method.side_effect = lambda par: mocked_counts[id(par)][attr]

        self.expect_ranking(reliable, flaked_once, serial_flaker)

    def test_leader_bump(self):
        """ All else held equal, the most active leaders get priority. """
        # Both participants are MIT undergraduates, equally likely to flake
        novice = models.Participant(affiliation='MU', name='New Leader')
        veteran = models.Participant(affiliation='MU', name='Veteran Leader')
        self.ranker.flake_factor.return_value = 0

        # Key difference: the veteran leader has a greater balance of led trips
        mocked_counts = {
            id(veteran): {'number_trips_led': 4, 'number_ws_trips': 1},  # Net 3
            id(novice):  {'number_trips_led': 2, 'number_ws_trips': 3}  # Net -1
        }

        def by_participant(attribute):
            """ Quick closure for looking up the count. """
            return lambda par: mocked_counts[id(par)][attribute]

        for attr in ['number_ws_trips', 'number_trips_led']:
            getattr(self.ranker, attr).side_effect = by_participant(attr)

        # Sanity check that our net trips led balance works properly
        self.assertEqual(self.ranker.trips_led_balance(veteran), 3)
        self.assertEqual(self.ranker.trips_led_balance(novice), 0)

        # Veteran is given higher ranking
        self.expect_ranking(veteran, novice)

    def test_sort_key_randomness(self):
        """ We break ties with a random value. """
        tweedle_dee = models.Participant(affiliation='NG')
        tweedle_dum = models.Participant(affiliation='NG')

        # All other ranking factors are equal
        self.ranker.number_trips_led.return_value = 0
        self.ranker.flake_factor.return_value = -2
        self.ranker.number_ws_trips.return_value = 3

        # Despite their equality, some randomness distinguishes keys
        dee_key = self.ranker.priority_key(tweedle_dee)
        dum_key = self.ranker.priority_key(tweedle_dum)
        self.assertNotEqual(dee_key, dum_key)
        self.assertEqual(dee_key[:-1], dum_key[:-1])  # (last item is random)


class SingleTripLotteryTests(SimpleTestCase):
    @patch.object(models.Trip, 'save')
    def test_fcfs_not_run(self, save_trip):
        """ If a trip's algorithm is not 'lottery', nothing happens. """
        trip = models.Trip(algorithm='fcfs')
        runner = lottery.SingleTripLotteryRunner(trip)

        trip.algorithm = 'fcfs'
        runner()  # Early exits because it's not a lottery trip
        save_trip.assert_not_called()
