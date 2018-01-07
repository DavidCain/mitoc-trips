from django.db.models import Q

from ws import models


def get_cars(trip):
    """ Return cars of specified drivers, otherwise all drivers' cars.

    If a trip leader says who's driving in the trip itinerary, then
    only return those participants' cars. Otherwise, gives all cars.
    The template will give a note specifying if these were the drivers
    given by the leader, of if they're all possible drivers.
    """
    signups = trip.signup_set.filter(on_trip=True)
    par_on_trip = (Q(participant__in=trip.leaders.all()) |
                   Q(participant__signup__in=signups))
    cars = models.Car.objects.filter(par_on_trip).distinct()
    if trip.info:
        cars = cars.filter(participant__in=trip.info.drivers.all())
    return cars.select_related('participant__lotteryinfo')
