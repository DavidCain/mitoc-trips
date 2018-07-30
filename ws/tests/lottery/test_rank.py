import itertools
from unittest.mock import patch

from django.test import SimpleTestCase

from ws.lottery import rank
from ws import models


class ParticipantRankingTests(SimpleTestCase):
    """ Test the logic by which we determine users with "first pick" status. """
    mocked_par_methods = ['number_trips_led', 'number_ws_trips', 'flake_factor']

    def setUp(self):
        base = 'ws.lottery.run.WinterSchoolParticipantRanker'
        patches = [patch(f'{base}.{name}') for name in self.mocked_par_methods]

        for patched in patches:
            patched.start()
        for patched in reversed(patches):
            self.addCleanup(patched.stop)

        # (Mocked-out methods accessible at self.ranker.<method_name>)
        self.ranker = rank.WinterSchoolParticipantRanker()

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
