import random
from collections import namedtuple
from datetime import timedelta

from django.db.models import Q
from mitoc_const import affiliations

from ws import enums, models, settings
from ws.utils.dates import local_now

from . import annotate_reciprocally_paired

WEIGHTS = {
    affiliations.MIT_UNDERGRAD.CODE: 0.3,
    affiliations.MIT_GRAD_STUDENT.CODE: 0.2,
    affiliations.MIT_AFFILIATE.CODE: 0.1,
    affiliations.MIT_ALUM.CODE: 0.1,
    affiliations.NON_MIT_UNDERGRAD.CODE: 0.0,
    affiliations.NON_MIT_GRAD_STUDENT.CODE: 0.0,
    affiliations.NON_AFFILIATE.CODE: 0.0,
}
assert set(WEIGHTS) == {aff.CODE for aff in affiliations.ALL}

# Old, deprecated status codes
WEIGHTS['M'] = WEIGHTS[affiliations.MIT_AFFILIATE.CODE]
WEIGHTS['N'] = WEIGHTS[affiliations.NON_AFFILIATE.CODE]
WEIGHTS['S'] = 0.0


def seed_for(participant, lottery_key):
    """ Return a seed to deterministically fetch pseudo-random numbers.

    We want participants to be ranked based on (mostly) random criteria, but we
    also want the ability to deterministically figure the results of a lottery
    run in a test run. This method enables us to do both.

    The seed must have the following properties:

    1. Cannot be reasonably guessed or inferred by any malicious participants.
        - If a participant can deduce their seed for a given lottery, they
          could feasibly take action to obtain a "better" seed by changing
          something about their participant record (e.g. obtaining a new PK by
          making a new account).
    2. Is deterministic for a given lottery run
        - Before running Winter School lotteries, it's standard practice to
          perform a test run locally. Because there was some randomness inherent
          in ranking, we could never be confident that the "real" run would return
          the same results. Introducing determinism allows us to ensure that our
          test run will have the same properties as the real run.
    3. Is unique for every participant, every lottery run
        - Participants deserve a fresh seed on each lottery run. If, for
          example, they had the same seed for a whole day, that would give them
          either consistently favorable or consistently unfavorably keys. For
          fairness, each lottery (single trip lotteries, or the WS lottery), must
          have their own seed.
        - Participants must have their own seed, for obvious reasons (they'd all be
          ranked exactly the same otherwise!)
    4. NOT be cryptographically secure
        - CPRNG's are, by design, not deterministic from a given seed. This is an
          unacceptable trait, since we're aiming for reproducibility. Because this
          seed is not used for security purposes, it's okay to use Python's
          Mersenne Twister algorithm (which is not a CPRNG) with this seed.

    Params:
        participant: Person the seed is being generated for
        lottery_key: Some key that is unique to this lottery run
            WARNING: If reused with a previous lottery run, the participant will
                     have the exact same random rank, which may affect lottery outcome.
    """
    if not participant.pk:
        raise ValueError("Can only get seed for participants saved to db!")
    return f"{participant.pk}-{lottery_key}-{settings.PRNG_SEED_SECRET}"


def affiliation_weighted_rand(participant, lottery_key):
    """ Return a float that's meant to rank participants by affiliation.

    A lower number is a "preferable" affiliation. That is to say, ranking
    participants by the result of this function will put MIT students towards
    the beginning of the list more often than not.

    See `seed_for` for a full explanation of `lottery_key`.
    """
    random.seed(seed_for(participant, lottery_key))
    return random.random() - WEIGHTS[participant.affiliation]


class ParticipantRanker:
    def __iter__(self):
        """ Participants in the order they should be placed, with their score.

        We sort participants by a scoring algorithm. The results of this
        scoring algorithm are useful when investigating the logs of a lottery
        run.

        Each participant is decorated with an attribute that says if they've
        reciprocally paired themselves with another participant.
        """
        participants = annotate_reciprocally_paired(self.participants_to_handle())
        with_keys = ((self.priority_key(par), par) for par in participants)
        for priority_key, participant in sorted(with_keys):
            yield participant, priority_key

    def participants_to_handle(self):
        """ QuerySet of participants to be ranked. """
        raise NotImplementedError

    def priority_key(self, participant):
        """ Return a key that can be used to sort the participant. """
        raise NotImplementedError


class SingleTripParticipantRanker(ParticipantRanker):
    def __init__(self, trip):
        self.trip = trip

    def priority_key(self, participant):
        lottery_key = f"trip-{self.trip.pk}"
        return affiliation_weighted_rand(participant, lottery_key)

    def participants_to_handle(self):
        return models.Participant.objects.filter(signup__trip=self.trip)


TripCounts = namedtuple('TripCounts', ['attended', 'flaked', 'total'])


WinterSchoolPriorityRank = namedtuple(
    'WinterSchoolPriorityRank',
    ['adjustment', 'flake_factor', 'leader_bump', 'affiliation_weight'],
)


class WinterSchoolParticipantRanker(ParticipantRanker):
    def __init__(self, execution_datetime=None):
        # It's important that we be able to simulate the future time with `execution_datetime`
        # If test-running the lottery in advance, we want the same ranking to be used later
        self.lottery_runtime = execution_datetime or local_now()
        today = self.lottery_runtime.date()
        self.today = today  # Silences a weird pylint error
        self.jan_1st = self.today.replace(month=1, day=1)
        self.lottery_key = f"ws-{today.isoformat()}"

    def get_rank_override(self, participant):
        if not hasattr(self, 'adjustments_by_participant'):
            adjustments = models.LotteryAdjustment.objects.filter(
                expires__gt=self.lottery_runtime
            )
            self.adjustments_by_participant = dict(
                adjustments.values_list('participant_id', 'adjustment')
            )
        return self.adjustments_by_participant.get(participant.pk, 0)

    def participants_to_handle(self):
        # For simplicity, only look at participants who actually have signups
        return models.Participant.objects.filter(
            signup__trip__trip_date__gt=self.today,
            signup__trip__algorithm='lottery',
            signup__trip__program=enums.Program.WINTER_SCHOOL.value,
        ).distinct()

    def priority_key(self, participant):
        """ Rank participants by:

        1. Manual overrides (rare, should not apply for >99% of participants)
        2. flakiness (having flaked with offsetting attendence -> lower priority)
        3. leader activity (active leaders get a boost in the lottery)
        4. affiliation (MIT affiliated is higher priority)
        5. randomness (factored into an affiliation weighting, breaks ties)
        """
        override = self.get_rank_override(participant)

        flake_factor = self.flake_factor(participant)
        # If we use raw flake factor, participants who've been on trips
        # will have an advantage over those who've been on none
        flaky_or_neutral = max(flake_factor, 0)

        # If the leader led more trips, give them a bump
        leader_bump = -self.trips_led_balance(participant)

        # Ties are resolved by a random number
        # (MIT students/affiliates are more likely to come first)
        affiliation_weight = affiliation_weighted_rand(participant, self.lottery_key)

        # Lower = higher in the list
        return WinterSchoolPriorityRank(
            override, flaky_or_neutral, leader_bump, affiliation_weight
        )

    def flake_factor(self, participant):
        """ Return a number indicating past "flakiness".

        A lower score indicates a more reliable participant.
        """
        attended, flaked, _ = self.number_ws_trips(participant)
        return (flaked * 5) - (2 * attended)

    @staticmethod
    def trips_flaked(participant):
        """ Return a QuerySet of trip pk's on which the participant flaked. """
        return (
            participant.feedback_set.filter(
                showed_up=False, trip__program=enums.Program.WINTER_SCHOOL.value
            )
            .values_list('trip__pk', flat=True)
            .distinct()
        )

    def number_trips_led(self, participant):
        """ Return the number of trips the participant has recently led.

        (If we considered all the trips the participant has ever led,
        participants could easily jump the queue every Winter School if they
        just lead a few trips once and then stop).
        """
        last_year = self.today - timedelta(days=365)
        within_last_year = Q(trip_date__gt=last_year, trip_date__lt=self.today)
        return participant.trips_led.filter(within_last_year).count()

    def number_ws_trips(self, participant):
        """ Count trips the participant attended, flaked, and the total.

        More specifically, this returns the total number of trips where the participant
        signed up and was expected to attend.

        In each of these cases, the trip should count towards the total:
        - Participant signed up for trip, showed up
        - Participant flaked, so leader removed them & left feedback
        - Participant flaked. Leader left feedback, but left them on the trip
        """
        marked_on_trip = set(
            participant.trip_set.filter(program=enums.Program.WINTER_SCHOOL.value)
            .filter(trip_date__gt=self.jan_1st, trip_date__lt=self.today)
            .values_list('pk', flat=True)
        )
        flaked = set(self.trips_flaked(participant))

        # Some leaders mark flakes, but don't remove participants
        # To calculate total, we can't double-count trips
        total = marked_on_trip.union(flaked)
        attended = total - flaked  # Only count if `on_trip` _and_ didn't flake

        return TripCounts(len(attended), len(flaked), len(total))

    def trips_led_balance(self, participant):
        """ Especially active leaders get priority. """
        _, _, total = self.number_ws_trips(participant)
        surplus = self.number_trips_led(participant) - total
        return max(surplus, 0)  # Don't penalize anybody for a negative balance

    def lowest_non_driver(self, trip):
        """ Return the lowest priority non-driver on the trip. """
        no_car = Q(participant__lotteryinfo__isnull=True) | Q(
            participant__lotteryinfo__car_status='none'
        )
        non_drivers = trip.signup_set.filter(no_car, on_trip=True)
        return max(
            non_drivers, key=lambda signup: self.priority_key(signup.participant)
        )
