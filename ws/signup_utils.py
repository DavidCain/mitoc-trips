from django.contrib.messages import add_message, ERROR, SUCCESS
from django.db.models import Q

from ws import models


def trip_or_wait(signup, request=None):
    if signup.on_trip:  # Sanity check
        add_message(request, ERROR, "Already on trip!")
        return

    trip = signup.trip
    if trip.signups_open and trip.algorithm == 'fcfs':
        if trip.open_slots:  # There's room, sign them up!
            signup.on_trip = True
            signup.save()
            request and add_message(request, SUCCESS, "Signed up!")
        else:  # If no room, add them to the waiting list
            try:  # Check if already on waiting list (do nothing if so)
                models.WaitListSignup.objects.get(signup=signup)
            except models.WaitListSignup.DoesNotExist:
                models.WaitListSignup.objects.create(signup=signup,
                                                    waitlist=trip.waitlist)
                request and add_message(request, SUCCESS, "Added to waitlist.")
    elif request:
        trip_not_eligible = "Trip is not an open first-come, first-serve trip"
        add_message(request, ERROR, trip_not_eligible)


def non_trip_participants(trip, exclude_only_non_trip=True):
    """ All participants not currently on a trip. """
    all_participants = models.Participant.objects.all()
    if exclude_only_non_trip:
        signups = trip.signup_set.filter(on_trip=True)
    par_on_trip = (Q(leader__in=trip.leaders.all()) |
                   Q(signup__in=signups))
    return all_participants.exclude(par_on_trip)


def prioritize_wl_signup(waitlist_signup, top_spot=False):
    """ Add the signup towards the top of the list.

    If top_spot=True, place above all wailist spots. Otherwise,
    place below all other previous priority waitlist spots, but above
    standard waitlist entries.

    A standard use case for this is when a participant is displaced by a driver
    (they were on the trip, so they should go to the top of the waitlist).
    """
    wl = waitlist_signup.waitlist
    if top_spot:
        waitlist_signup.manual_order = wl.first_of_priority
    else:
        waitlist_signup.manual_order = wl.last_of_priority
    waitlist_signup.save()
