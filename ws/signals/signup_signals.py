"""
Handle aspects of trip creation/modification when receiving signup changes.
"""
from __future__ import unicode_literals

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from ws.models import SignUp, WaitListSignup


@receiver(post_save, sender=SignUp)
def new_fcfs_signup(sender, instance, created, raw, using, update_fields, **kwargs):
    """ Handles first-come, first-serve signups:

        When a participant tries to sign up, put them on the trip, or its waiting list.
    """
    return trip_or_wait(instance, created)


def trip_or_wait(signup, created):
    if created and signup.trip.algorithm == 'fcfs':
        if signup.trip.open_slots:  # There's room, sign them up!
            print "{} is on '{}'.".format(signup.participant, signup.trip)
            signup.on_trip = True
            signup.save()
        else:  # If no room, add them to the waiting list
            print "Putting {} on the waiting list for '{}'.".format(signup.participant, signup.trip)
            # TODO: Signals documentation warns against modifying database
            # (rationale is unclear). While signals are threadsafe, this may
            # cause issues.
            WaitListSignup.objects.create(signup=signup,
                                          waitlist=signup.trip.waitlist)


@receiver(pre_delete, sender=SignUp)
def free_spot_on_trip(sender, instance, using, **kwargs):
    """ When somebody drops off a trip, bump up the top waitlist signup. """
    if instance.on_trip and instance.trip.algorithm == 'fcfs':
        first_signup = instance.trip.waitlist.signups.first()
        first_signup.on_trip = True
        first_signup.waitlistsignup.delete()
        first_signup.save()
