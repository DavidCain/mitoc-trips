from django.contrib.messages import add_message, ERROR, SUCCESS

from ws import models


def trip_or_wait(signup, request=None):
    trip = signup.trip
    if trip.signups_open and trip.algorithm == 'fcfs':
        if trip.open_slots:  # There's room, sign them up!
            signup.on_trip = True
            signup.save()
            request and add_message(request, SUCCESS, "Signed up!")
        else:  # If no room, add them to the waiting list
            models.WaitListSignup.objects.create(signup=signup,
                                                 waitlist=trip.waitlist)
            request and add_message(request, SUCCESS, "Added to waitlist.")
    elif request:
        trip_not_eligible = "Trip is not an open first-come, first-serve trip"
        add_message(request, ERROR, trip_not_eligible)
