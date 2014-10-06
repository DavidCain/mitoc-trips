"""
Handle aspects of trip creation/modification when receiving signup changes.
"""
from __future__ import unicode_literals

from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.db.models.signals import post_save, pre_delete, m2m_changed
from django.dispatch import receiver

from ws.models import SignUp, WaitList, WaitListSignup, Trip


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
        trip = instance.trip
        first_signup = trip.waitlist.signups.first()
        first_signup.on_trip = True
        first_signup.waitlistsignup.delete()
        first_signup.save()

        trip_link = get_trip_link(trip)
        send_mail("You're signed up for {}".format(trip),
                  "You're on {}! If you can't make it, please remove yourself "
                  "from the trip so others can join.".format(trip_link),
                  trip.creator.participant.email,
                  [first_signup.participant.email],
                  fail_silently=True)


def get_trip_link(trip):
    trip_url = reverse('view_trip', args=(trip.id,))
    #return '<a href="{}">"{}"</a>'.format(trip_url, trip)
    return trip  # TODO: The link above only does relative URL


@receiver(post_save, sender=Trip)
def add_waitlist(sender, instance, created, raw, using, update_fields, **kwargs):
    if created:
        instance.waitlist = WaitList.objects.create(trip=instance)
        instance.save()


@receiver(m2m_changed, sender=Trip.leaders.through)
def inform_leaders(sender, instance, action, reverse, model, pk_set, using,
                   **kwargs):
    """ Inform all leaders that they're on a given trip.

    Emails will be sent any time a new leader is added to the ManyToMany
    relation (that is, at trip creation, or if a new Leader is added).
    All messages come from the trip creator.

    Nothing happens if former leaders are removed.
    """
    if action == 'post_add':
        for leader in instance.leaders.all():
            send_coleader_email(instance, leader)


def send_coleader_email(trip, leader):
    trip_link = get_trip_link(trip)
    send_mail("You're a leader on {}".format(trip),
              # TODO: What information should be contained in this message?
              "You're leading '{}' on {}.".format(trip_link, trip.trip_date),
              trip.creator.participant.email,
              [leader.participant.email],
              fail_silently=True)
