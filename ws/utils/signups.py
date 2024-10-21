import contextlib

from django.contrib import messages
from django.db import transaction
from django.db.models import Q, QuerySet
from django.http import HttpRequest

from ws import models


def next_in_order(signup: models.SignUp, manual_order: int | None = None) -> None:
    """Add the signup to the next-ordered spot on the trip or in waitlist.

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


@transaction.atomic
def add_to_waitlist(
    signup: models.SignUp,
    request: HttpRequest | None = None,
    prioritize: bool = False,
    top_spot: bool = False,
) -> models.WaitListSignup:
    """Add the given signup to the waitlist, optionally prioritizing it."""
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
        _prioritize_wl_signup(wl_signup, top_spot)
    return wl_signup


def trip_or_wait(
    signup: models.SignUp,
    request: HttpRequest | None = None,
    prioritize: bool = False,
    top_spot: bool = False,
    trip_must_be_open: bool = False,
) -> models.SignUp:
    """Given a signup object, attempt to place the participant on the trip.

    If the trip is full, instead place that person on the waiting list.

    Args:
    ----
    signup: Signup object to add to the trip *or* the waitlist
    request: If given, will supply messages to the request
    prioritize: Give any waitlist signup priority
    top_spot: Give any waitlist signup top priority
    trip_must_be_open: If true, don't sign up on closed trip

    """
    trip = signup.trip
    if signup.on_trip:
        return signup

    eligible = trip.algorithm == "fcfs" and (trip.signups_open or not trip_must_be_open)
    if not eligible:
        if request:
            messages.error(request, "Trip is not an open first-come, first-serve trip")
        return signup

    if not trip.open_slots:  # Trip is full, add to the waiting list
        add_to_waitlist(signup, request, prioritize, top_spot)
        return signup

    signup.on_trip = True
    signup.save()
    if request:
        messages.success(request, "Signed up!")

    # Since the participant is now on the trip, we should be sure to remove any waitlist
    with contextlib.suppress(models.WaitListSignup.DoesNotExist):
        signup.waitlistsignup.delete()

    return signup


def update_queues_if_trip_open(trip: models.Trip) -> None:
    """Update queues if the trip is an open, first-come, first-serve trip.

    This is intended to be used when the trip size changes (either from changing
    the maximum participants, or from somebody else dropping off).
    """
    if not (trip.signups_open and trip.algorithm == "fcfs"):
        return

    on_trip = trip.signup_set.filter(on_trip=True)
    diff = trip.maximum_participants - on_trip.count()

    waitlisted = models.WaitListSignup.objects.filter(signup__trip=trip)
    if diff > 0:  # Trip is growing, add waitlisted participants if applicable
        for waitlist_signup in waitlisted[:diff]:
            trip_or_wait(waitlist_signup.signup)
    elif diff < 0:  # Trip is shrinking, move lowest signups to waitlist
        for _ in range(abs(diff)):
            last = trip.signup_set.filter(on_trip=True).last()
            assert last is not None  # TODO: Don't use implicit ordering, use `latest()`
            last.on_trip = False
            last.save()
            # Make sure they're at the top!
            add_to_waitlist(last, prioritize=True, top_spot=True)


def non_trip_participants(trip: models.Trip) -> QuerySet[models.Participant]:
    """All participants not currently on the given trip."""
    all_participants = models.Participant.objects.all()
    signups = trip.signup_set.filter(on_trip=True)
    par_on_trip = Q(pk__in=trip.leaders.all()) | Q(signup__in=signups)
    return all_participants.exclude(par_on_trip)


def _prioritize_wl_signup(
    waitlist_signup: models.WaitListSignup,
    top_spot: bool = False,
) -> None:
    """Add the signup towards the top of the list.

    If top_spot=True, place above all waitlist spots. Otherwise,
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
