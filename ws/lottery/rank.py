from collections import namedtuple
from datetime import timedelta
import random

from django.db.models import F, Q, Case, When, IntegerField

from mitoc_const import affiliations

from ws import models
from ws.utils.dates import local_date, jan_1


WEIGHTS = {
    affiliations.MIT_UNDERGRAD.CODE:    0.3,
    affiliations.MIT_GRAD_STUDENT.CODE: 0.2,
    affiliations.MIT_AFFILIATE.CODE:    0.1,
    affiliations.MIT_ALUM.CODE:         0.1,
    affiliations.NON_MIT_UNDERGRAD.CODE:    0.0,
    affiliations.NON_MIT_GRAD_STUDENT.CODE: 0.0,
    affiliations.NON_AFFILIATE.CODE:        0.0,
}
assert set(WEIGHTS) == {aff.CODE for aff in affiliations.ALL}

# Old, deprecated status codes
WEIGHTS['M'] = WEIGHTS[affiliations.MIT_AFFILIATE.CODE]
WEIGHTS['N'] = WEIGHTS[affiliations.NON_AFFILIATE.CODE]
WEIGHTS['S'] = 0.0


def affiliation_weighted_rand(participant):
    """ Return a float that's meant to rank participants by affiliation.

    A lower number is a "preferable" affiliation. That is to say, ranking
    participants by the result of this function will put MIT students towards
    the beginning of the list more often than not.
    """
    return random.random() - WEIGHTS[participant.affiliation]


class ParticipantRanker:
    def __iter__(self):
        return iter(self.ranked_participants())

    def participants_to_handle(self):
        """ QuerySet of participants to be ranked. """
        raise NotImplementedError

    def priority_key(self, participant):
        """ Return a key that can be used to sort the participant. """
        raise NotImplementedError

    def ranked_participants(self):
        """ Participants in the order they should be placed.

        Each participant is decorated with an attribute that says if they've
        reciprocally paired themselves with another participant.
        """
        is_reciprocally_paired = (
            Q(pk=F('lotteryinfo__paired_with__'
                   'lotteryinfo__paired_with__pk'))
        )

        participants = self.participants_to_handle().annotate(
            reciprocally_paired=Case(
                When(is_reciprocally_paired, then=1),
                default=0,
                output_field=IntegerField()
            )
        )
        return sorted(participants, key=self.priority_key)


class SingleTripParticipantRanker(ParticipantRanker):
    def __init__(self, trip):
        self.trip = trip

    def priority_key(self, participant):
        return affiliation_weighted_rand(participant)

    def participants_to_handle(self):
        return models.Participant.objects.filter(signup__trip=self.trip)


TripCounts = namedtuple('TripCounts', ['attended', 'flaked', 'total'])


class WinterSchoolParticipantRanker(ParticipantRanker):
    def __init__(self):
        self.today = local_date()
        self.jan_1st = jan_1()

    def participants_to_handle(self):
        # For simplicity, only look at participants who actually have signups
        return models.Participant.objects.filter(
            signup__trip__trip_date__gt=self.today,
            signup__trip__algorithm='lottery',
            signup__trip__activity='winter_school'
        ).distinct()

    def priority_key(self, participant):
        """ Rank participants by:

        1. number of trips (fewer -> higher priority)
        2. affiliation (MIT affiliated is higher priority)
        3. 'flakiness' (more flakes -> lower priority
        """
        flake_factor = self.flake_factor(participant)
        # If we use raw flake factor, participants who've been on trips
        # will have an advantage over those who've been on none
        flaky_or_neutral = max(flake_factor, 0)

        # If the leader led more trips, give them a bump
        leader_bump = -self.trips_led_balance(participant)

        # Ties are resolved by a random number
        # (MIT students/affiliates are more likely to come first)
        affiliation_weight = affiliation_weighted_rand(participant)

        # Lower = higher in the list
        return (flaky_or_neutral, leader_bump, affiliation_weight)

    def flake_factor(self, participant):
        """ Return a number indicating past "flakiness".

        A lower score indicates a more reliable participant.
        """
        attended, flaked, _ = self.number_ws_trips(participant)
        return (flaked * 5) - (2 * attended)

    def trips_flaked(self, participant):
        """ Return a QuerySet of trip pk's on which the participant flaked. """
        return participant.feedback_set.filter(
            showed_up=False, trip__activity='winter_school'
        ).values_list('trip__pk', flat=True).distinct()

    def number_trips_led(self, participant):
        """ Return the number of trips the participant has recently led.

        (If we considered all the trips the participant has ever led,
        participants could easily jump the queue every Winter School if they
        just lead a few trips once and then stop).
        """
        last_year = local_date() - timedelta(days=365)
        return participant.trips_led.filter(trip_date__gt=last_year).count()

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
            participant.trip_set
            .filter(activity='winter_school')
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
        no_car = (Q(participant__lotteryinfo__isnull=True) |
                  Q(participant__lotteryinfo__car_status='none'))
        non_drivers = trip.signup_set.filter(no_car, on_trip=True)
        return max(non_drivers, key=lambda signup: self.priority_key(signup.participant))
