from __future__ import unicode_literals

import random

from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils import timezone
import pytz

from ws import dateutils
from ws import models
from datetime import date, timedelta


today = dateutils.local_now().date()
jan_1st = date(today.year, 1, 1)
pytz_timezone = timezone.get_default_timezone()


class Command(BaseCommand):
    def handle(self, *args, **options):
        assign_trips()
        free_for_all()


def get_prioritized_participants():
    """ Return ordered list of participants, ranked by:
            - number of trips (fewer -> higher priority)
            - affiliation (MIT affiliated is higher priority)
            - 'flakiness' (more flakes -> lower priority
    """
    participants = models.Participant.objects.filter(attended_lectures=True)
    return sorted(participants, key=priority_key)


def get_number_of_trips(participant):
    """ Number of trips the participant has been on this year. """
    signups = participant.signup_set.filter(trip__trip_date__gt=jan_1st)
    return sum(signup.on_trip for signup in signups)


def get_flake_factor(participant):
    """ Return a number indicating past "flakiness".

    A lower score indicates a more reliable participant.
    """
    score = 0
    for feedback in participant.feedback_set.all():
        score += 5 if not feedback.showed_up else -2
    return score


def priority_key(participant):
    """ Return tuple for sorting participants. """
    flake_factor = get_flake_factor(participant)
    # If we use raw flake factor, participants who've been on trips
    # will have an advantage over those who've been on none
    flaky_or_neutral = max(flake_factor, 0)
    number_of_trips = get_number_of_trips(participant)
    affiliation = ['S', 'M', 'N'].index(participant.affiliation)

    # Lower = higher in the list
    # Random float faily resolves ties without using database order
    return (flaky_or_neutral, number_of_trips, affiliation, random.random())


def lowest_non_driver(trip):
    """ Return the lowest priority non-driver on the trip. """
    accepted_signups = trip.signup_set.filter(on_trip=True)
    non_driver_kwargs = {'participant__lotteryinfo__car_status': 'none'}
    non_drivers = accepted_signups.filter(**non_driver_kwargs)
    return max(non_drivers, key=lambda signup: priority_key(signup.participant))


def add_to_waitlist(signup):
    """ Put a given signup on its corresponding trip's wait list. """
    print "Adding {} to the waiting list for {}.".format(signup.participant, signup.trip)
    signup.on_trip = False
    signup.save()

    # Ensure not already waitlisted
    try:
        if signup.waitlistsignup:
            return
    except ObjectDoesNotExist:
        pass

    # Fetch existing waitlist, or create a new one
    waitlist = signup.trip.waitlist

    # Add this signup to the waitlist
    models.WaitListSignup.objects.create(signup=signup, waitlist=waitlist)


def free_for_all():
    """ Make trips first-come, first-serve.

    Trips re-open Thursday at noon, close at midnight before trip.
    """
    print "Making all lottery trips first-come, first-serve"
    lottery_trips = models.Trip.objects.filter(algorithm='lottery')
    for trip in lottery_trips:
        trip.algorithm = 'fcfs'
        trip.signups_open_at = dateutils.thur_at_noon()
        day_before = trip.trip_date - timedelta(days=1)
        midnight = timezone.datetime(day_before.year, day_before.month,
                                     day_before.day, 23, 59, 59)
        trip.signups_close_at = pytz_timezone.localize(midnight)
        trip.save()


def assign_trips():
    # First-come, first-serve trips are separate from the lottery system
    for participant in get_prioritized_participants():
        handling_text = "Handling {}".format(participant)
        print handling_text
        print '-' * len(handling_text)
        handle_participant(participant)
        print


def handle_participant(participant):
    """ Handle assigning a single participant to a trip.

    Each participant is assigned to a maximum of one trip. If no
    trips are open, they are waitlisted on their highest priority trip.
    """
    try:
        driver = participant.lotteryinfo.is_driver
    except AttributeError:  # No lottery form submission
        driver = False

    # Only consider lottery signups for future trips
    signups = participant.signup_set.filter(trip__trip_date__gt=today,
                                            trip__algorithm='lottery')
    if not signups:
        print "{} did not choose any trips this week".format(participant)
        return

    # Place participant on their first choice available trip
    for signup in signups.order_by('order', 'time_created'):
        trip = signup.trip
        if trip.open_slots:
            print "{} has {} slot(s), adding {}".format(trip, trip.open_slots, participant)
            signup.on_trip = True
            signup.save()
            break
        elif driver and not trip.open_slots:
            # A driver may displace somebody else
            is_driver = Q(participant__lotteryinfo__car_status__in=['own', 'rent'])
            participant_drivers = trip.signup_set.filter(is_driver, on_trip=True)
            lottery_leaders = trip.leaders.filter(participant__lotteryinfo__isnull=False)
            leader_drivers = sum(leader.participant.lotteryinfo.is_driver
                                 for leader in lottery_leaders)
            if (participant_drivers.count() + leader_drivers) < 2:
                print "{} is full, but doesn't have two drivers".format(trip)
                print "Adding {} to '{}', as they're a driver".format(signup, trip)
                add_to_waitlist(lowest_non_driver(trip))
                signup.on_trip = True
                signup.save()
                break
        else:
            print "Can't place {} on {}".format(participant, trip)

    else:  # No trips are open
        print "None of {}'s trips are open.".format(participant)
        favorite_signup = signups.first()
        add_to_waitlist(favorite_signup)
