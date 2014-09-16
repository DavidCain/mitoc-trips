from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.utils import timezone

from ws import models
from datetime import date, timedelta


today = date.today()
jan_1st = date(today.year, 1, 1)


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
    number_of_trips = get_number_of_trips(participant)
    not_mit_affiliated = participant.affiliation == 'N'

    # Lower = higher in the list
    return (flake_factor, number_of_trips, not_mit_affiliated)


def lowest_non_driver(trip):
    """ Return the lowest priority non-driver on the trip. """
    accepted_signups = trip.signup_set.filter(on_trip=True)
    non_driver_kwargs = {'participant__lotteryinfo__own_a_car': False,
                         'participant__lotteryinfo__willing_to_rent': False}
    non_drivers = accepted_signups.filter(**non_driver_kwargs)
    return max(non_drivers, key=lambda signup: priority_key(signup.participant))


def add_to_waitlist(signup):
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
    try:
        waitlist = signup.trip.waitlist
    except ObjectDoesNotExist:
        signup.trip.waitlist = models.WaitList.objects.create(trip=signup.trip)
        waitlist = signup.trip.waitlist

    # Add this signup to the waitlist
    models.WaitListSignup.objects.create(signup=signup, waitlist=waitlist)


def free_for_all():
    """ Make trips first-come, first-serve, open them for another 24 hours. """
    print "Making all lottery trips first-come, first-serve"
    lottery_trips = models.Trip.objects.filter(algorithm='lottery')
    for trip in lottery_trips:
        trip.algorithm = 'fcfs'
        trip.signups_close_at = timezone.now() + timedelta(days=1)
        trip.save()


def assign_trips():
    # First-come, first-serve trips are separate from the lottery system
    for participant in get_prioritized_participants():
        print "Handling {}".format(participant)
        print 12 * '-'
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
        accepted_signups = trip.signup_set.filter(on_trip=True)
        empty_slots = trip.capacity - accepted_signups.count()
        if empty_slots:
            print "{} has {} slot(s), adding {}".format(trip, empty_slots, participant)
            signup.on_trip = True
            signup.save()
            break
        elif driver and not empty_slots:
            # A driver may displace somebody else
            is_driver = (Q(participant__lotteryinfo__own_a_car=True) |
                         Q(participant__lotteryinfo__willing_to_rent=True))

            drivers = accepted_signups.filter(is_driver)
            if drivers.count() < 2:
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
