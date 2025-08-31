from django.db.models import Q, QuerySet

from ws import models


def approve_trip(
    trip: models.Trip,
    *,
    approving_chair: models.Participant,
    trip_edit_revision: int,
    notes: str = "",
) -> None:
    """Mark a trip as approved, even if it already *has* been approved!"""
    # No lock necessary, this should always be an *increasing* integer.
    assert trip.edit_revision >= trip_edit_revision, (
        f"Trip #{trip.pk} has no version {trip_edit_revision}"
    )
    # It's fine if the trip is edited mid-execution of this function.
    trip.chair_approved = True
    trip.save()
    models.ChairApproval(
        trip=trip,
        approver=approving_chair,
        trip_edit_revision=trip.edit_revision,
        notes=notes,
    ).save()


def get_cars(trip: models.Trip) -> QuerySet[models.Car]:
    """Return cars of specified drivers, otherwise all drivers' cars.

    If a trip leader says who's driving in the trip itinerary, then
    only return those participants' cars. Otherwise, gives all cars.
    The template will give a note specifying if these were the drivers
    given by the leader, of if they're all possible drivers.
    """
    signups = trip.signup_set.filter(on_trip=True)
    par_on_trip = Q(participant__in=trip.leaders.all()) | Q(
        participant__signup__in=signups
    )
    cars = models.Car.objects.filter(par_on_trip).distinct()
    if trip.info:
        cars = cars.filter(participant__in=trip.info.drivers.all())
    return cars.select_related("participant__lotteryinfo")
