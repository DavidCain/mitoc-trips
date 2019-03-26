from django.contrib import messages
from django.db.models import Q

from ws import models


def next_in_order(signup, manual_order=None):
    """ Add the signup to the next-ordered spot on the trip or in waitlist.

    Waitlists are ordered in reverse so that those without a manual override
    on their ordering (manual_order = None) will always appear below those that
    have a manual ordering (i.e. set by leaders).

    If specifying a manual order, use that with its intuitive meaning - that a
    lower ordering value means the signup shoud be prioritized, whether it's
    a normal signup or a waitlist signup.
    """
    if signup.on_trip:
        signup.manual_order = manual_order or signup.trip.last_of_priority
        signup.save()
        return

    try:
        wl = signup.waitlistsignup
    except models.WaitListSignup.DoesNotExist:
        return

    if manual_order:
        # pylint: disable=invalid-unary-operand-type
        wl.manual_order = -manual_order  # See WaitlistSignup.meta
    else:
        wl.manual_order = wl.waitlist.last_of_priority
    wl.save()


def add_to_waitlist(signup, request=None, prioritize=False, top_spot=False):
    """ Add the given signup to the waitlist, optionally prioritizing it. """
    signup.on_trip = False
    signup.save()

    try:
        wl_signup = signup.waitlistsignup
    except models.WaitListSignup.DoesNotExist:
        wl_signup = models.WaitListSignup.objects.create(
            signup=signup, waitlist=signup.trip.waitlist
        )
        if request:
            messages.success(request, "Added to waitlist.")

    if prioritize:
        prioritize_wl_signup(wl_signup, top_spot)
    return wl_signup


def trip_or_wait(
    signup, request=None, prioritize=False, top_spot=False, trip_must_be_open=False
):
    """ Given a signup object, attempt to place the participant on the trip.

    If the trip is full, instead place that person on the waiting list.

    :param request: If given, will supply messages to the request
    :param prioritize: Give any waitlist signup priority
    :param top_spot: Give any waitlist signup top priority
    :param trip_must_be_open: If true, don't sign up on closed trip
    """
    trip = signup.trip
    if signup.on_trip:
        return signup
    if trip.algorithm == 'fcfs' and (trip.signups_open or not trip_must_be_open):
        try:
            wl_signup = signup.waitlistsignup
        except models.WaitListSignup.DoesNotExist:
            wl_signup = None

        if trip.open_slots > 0:  # There's room, sign them up!
            signup.on_trip = True
            signup.save()
            if request:
                messages.success(request, "Signed up!")
            if wl_signup:
                wl_signup.delete()  # Remove (if applicable)
        else:  # If no room, add them to the waiting list
            add_to_waitlist(signup, request, prioritize, top_spot)
    elif request:
        trip_not_eligible = "Trip is not an open first-come, first-serve trip"
        messages.error(request, trip_not_eligible)
    return signup


def update_queues_if_trip_open(trip):
    """ Update queues if the trip is an open, first-come, first-serve trip. """
    if trip.signups_open and trip.algorithm == 'fcfs':
        update_signup_queues(trip)


def update_signup_queues(trip):
    """ Update the participant and waitlist queues for a trip.

    This is intended to be used when the trip size changes. If the size
    is the same, nothing will happen.
    """
    on_trip = trip.signup_set.filter(on_trip=True)
    diff = trip.maximum_participants - on_trip.count()

    waitlisted = models.WaitListSignup.objects.filter(signup__trip=trip)
    if diff > 0:  # Trip is growing, add waitlisted participants if applicable
        for waitlist_signup in waitlisted[:diff]:
            trip_or_wait(waitlist_signup.signup)
    elif diff < 0:  # Trip is shrinking, move lowest signups to waitlist
        for i in range(abs(diff)):
            last = trip.signup_set.filter(on_trip=True).last()
            trip_or_wait(last, prioritize=True, top_spot=True)


def non_trip_participants(trip):
    """ All participants not currently on the given trip. """
    all_participants = models.Participant.objects.all()
    signups = trip.signup_set.filter(on_trip=True)
    par_on_trip = Q(pk__in=trip.leaders.all()) | Q(signup__in=signups)
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
