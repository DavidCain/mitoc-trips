from datetime import date
import itertools
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from freezegun import freeze_time

from ws.lottery import rank
from ws import models
from ws.tests.factories import (
    FeedbackFactory, LotteryInfoFactory, ParticipantFactory, TripFactory
)


class TestRanker(rank.ParticipantRanker):
    def __init__(self, participant_pks):
        self.participant_pks = participant_pks

    def priority_key(self, participant):
        return participant.pk  # (Doesn't matter how they're ordered)

    def participants_to_handle(self):
        return models.Participant.objects.filter(pk__in=self.participant_pks)


class ParticipantPairingTests(TestCase):
    """ Test the logic on reciprocal participant pairing. """
    multi_db = True  # Roll back changes in _all_ databases

    def expect_pairing(self, expected):
        """ Run noted participants through ranking, expect pairing results. """
        par_pks = set(par.pk for par in expected)
        ranker = TestRanker(participant_pks=par_pks)
        actual = {par: bool(par.reciprocally_paired) for par in ranker}
        self.assertEqual(expected, actual)

    def test_no_lotteryinfo(self):
        """ No lottery info still counts as not being paired. """
        no_lotteryinfo = ParticipantFactory.create(lotteryinfo=None)
        self.expect_pairing({no_lotteryinfo: False})

    def test_on_their_own(self):
        """ Participants who don't request pairing aren't paired. """
        alone = LotteryInfoFactory.create(paired_with=None)
        self.expect_pairing({alone.participant: False})

    def test_unrequited_pairing(self):
        """ Pairing must be bidirectional to be acted upon. """
        wants_to_fly_solo = LotteryInfoFactory.create(paired_with=None)
        wants_to_be_together = LotteryInfoFactory.create(
            paired_with=wants_to_fly_solo.participant
        )
        self.expect_pairing({wants_to_fly_solo.participant: False,
                             wants_to_be_together.participant: False})

    def test_nulls_do_not_mean_equal(self):
        """ Participants that want no pairing aren't accidentallly paired.

        This checks an implementation detail, ensuring that null==null doesn't
        amount to the SQL query mistakenly regarding participants as paired.
        """
        no_lotteryinfo_1 = ParticipantFactory.create(lotteryinfo=None)
        no_lotteryinfo_2 = ParticipantFactory.create(lotteryinfo=None)
        alone_1 = LotteryInfoFactory.create(paired_with=None)
        alone_2 = LotteryInfoFactory.create(paired_with=None)

        self.expect_pairing({
            no_lotteryinfo_1: False,
            no_lotteryinfo_2: False,
            alone_1.participant: False,
            alone_2.participant: False,
        })

    def test_reciprocal_pairing(self):
        """ Two participants who request each other are reciprocally paired. """
        bonnie = ParticipantFactory.create()
        clyde = ParticipantFactory.create()
        LotteryInfoFactory.create(participant=bonnie, paired_with=clyde)
        LotteryInfoFactory.create(participant=clyde, paired_with=bonnie)
        self.expect_pairing({bonnie: True, clyde: True})


class ParticipantRankingTests(SimpleTestCase):
    """ Test the logic by which we determine users with "first pick" status. """
    mocked_par_methods = ['number_trips_led', 'number_ws_trips']

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
        serial_flaker = models.Participant(affiliation='MU', name='Serial Flaker')
        flaked_once = models.Participant(affiliation='MG', name='One-time Flaker')
        reliable = models.Participant(affiliation='NA', name='Reliable')

        # NOTE: Must use id since these objects have no pk (they're unhashable)
        mocked_counts = {
            id(flaked_once): {
                'number_trips_led': 8,
                'number_ws_trips': rank.TripCounts(attended=0, flaked=1, total=1)
            },
            id(serial_flaker): {
                'number_trips_led': 4,
                'number_ws_trips': rank.TripCounts(attended=0, flaked=3, total=3)
            },
            id(reliable): {
                'number_trips_led': 0,
                'number_ws_trips': rank.TripCounts(attended=4, flaked=0, total=4)
            },
        }

        self.ranker.number_trips_led.side_effect = lambda par: mocked_counts[id(par)]['number_trips_led']
        self.ranker.number_ws_trips.side_effect = lambda par: mocked_counts[id(par)]['number_ws_trips']

        self.expect_ranking(reliable, flaked_once, serial_flaker)

    def test_leader_bump(self):
        """ All else held equal, the most active leaders get priority. """
        # Both participants are MIT undergraduates, equally likely to flake
        novice = models.Participant(affiliation='MU', name='New Leader')
        veteran = models.Participant(affiliation='MU', name='Veteran Leader')

        def attended_all(num):
            return rank.TripCounts(attended=num, flaked=0, total=num)

        # Key difference: the veteran leader has a greater balance of led trips
        mocked_counts = {
            id(veteran): {'number_trips_led': 4, 'number_ws_trips': attended_all(1)},  # Net 3
            id(novice):  {'number_trips_led': 2, 'number_ws_trips': attended_all(3)}  # Net -1
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
        solid_record = rank.TripCounts(attended=3, flaked=0, total=3)
        self.ranker.number_ws_trips.return_value = solid_record

        # Despite their equality, some randomness distinguishes keys
        dee_key = self.ranker.priority_key(tweedle_dee)
        dum_key = self.ranker.priority_key(tweedle_dum)
        self.assertNotEqual(dee_key, dum_key)
        self.assertEqual(dee_key[:-1], dum_key[:-1])  # (last item is random)


@freeze_time("Wed, 24 Jan 2018 09:00:00 EST")  # Scheduled after 2nd week of WS
class FlakeFactorTests(TestCase):
    multi_db = True  # Roll back changes in _all_ databases

    def setUp(self):
        self.participant = ParticipantFactory.create()
        self.ranker = rank.WinterSchoolParticipantRanker()

    @classmethod
    def setUpTestData(cls):
        """ Create some trips to relate to the participant test object.

        (We do not start with the participant actually signed up/on the trip).
        """
        cls.last_season_trips = [
            TripFactory.create(activity='winter_school', trip_date=date(2017, 1, 15)),
            TripFactory.create(activity='winter_school', trip_date=date(2017, 1, 22))
        ]

        cls.three_trips = [
            TripFactory.create(activity='winter_school', trip_date=date(2018, 1, 13)),
            TripFactory.create(activity='winter_school', trip_date=date(2018, 1, 14)),
            TripFactory.create(activity='winter_school', trip_date=date(2018, 1, 20))
        ]
        cls.all_trips = cls.last_season_trips + cls.three_trips

    def test_previous_seasons_omitted(self):
        """ Only trips from the current Winter School are considered. """
        par_on_trip = {'participant': self.participant, 'on_trip': True}
        for trip in self.three_trips:
            models.SignUp.objects.create(trip=trip, **par_on_trip).save()

        self.assertEqual(self.ranker.number_ws_trips(self.participant),
                         rank.TripCounts(attended=3, flaked=0, total=3))

    def test_each_trip_counted_once(self):
        """ Multiple trip leaders declaring a participant a flake is no worse than 1. """
        flaked = {'participant': self.participant, 'showed_up': False}
        for trip in self.three_trips:
            for _ in range(3):
                FeedbackFactory.create(trip=trip, **flaked)

        self.assertEqual(self.ranker.number_ws_trips(self.participant),
                         rank.TripCounts(attended=0, flaked=3, total=3))

    def test_no_attendance(self):
        """ The flake factor is set to zero for participants with no trips. """
        self.assertFalse(self.participant.trip_set.exists())
        self.assertFalse(self.participant.feedback_set.exists())
        self.assertEqual(0, self.ranker.flake_factor(self.participant))

    def test_missed_each_trip(self):
        """ Missing multiple trips gives you a very poor score.  """
        # (Each SignUp object was deleted by trip leaders to indicate that the
        # participant never actually went on the trip)
        for trip in self.three_trips:
            FeedbackFactory.create(participant=self.participant, trip=trip,
                                   showed_up=False, comments="No show")

        self.assertEqual(self.ranker.number_ws_trips(self.participant),
                         rank.TripCounts(attended=0, flaked=3, total=3))
        self.assertEqual(15, self.ranker.flake_factor(self.participant))

    def test_perfect_attendance(self):
        """ Participants who've showed up for every trip score well.  """
        # (The only trips considered are past trips from the current Winter School)
        par_on_trip = {'participant': self.participant, 'on_trip': True}
        for trip in self.three_trips:
            models.SignUp.objects.create(trip=trip, **par_on_trip).save()

        # Count trips they attended, but for which they received no feedback
        self.assertEqual(-6, self.ranker.flake_factor(self.participant))

        # When explicitly noted as having attended, they receive the same score
        for trip in self.three_trips:
            FeedbackFactory.create(participant=self.participant,
                                   trip=trip, showed_up=True)
        self.assertEqual(-6, self.ranker.flake_factor(self.participant))

    def test_leader_disagreement(self):
        """ If only one leader reports them as flaking, that's a flake. """
        subject = {'participant': self.participant, 'trip': self.three_trips[0]}

        models.SignUp(on_trip=True, **subject).save()

        # One leader says the participant didn't show
        FeedbackFactory.create(showed_up=False, comments="No show", **subject)

        self.assertEqual(self.ranker.number_ws_trips(self.participant),
                         rank.TripCounts(attended=0, flaked=1, total=1))
        self.assertEqual(5, self.ranker.flake_factor(self.participant))

        # Co-leaders didn't note person a flake (most likely, didn't know how)
        FeedbackFactory.create(showed_up=True, **subject)
        FeedbackFactory.create(showed_up=True, **subject)

        # However, we still consider them to have flaked on the first trip
        self.assertEqual(self.ranker.number_ws_trips(self.participant),
                         rank.TripCounts(attended=0, flaked=1, total=1))
        self.assertEqual(5, self.ranker.flake_factor(self.participant))