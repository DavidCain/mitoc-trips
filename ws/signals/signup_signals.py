"""
Handle aspects of trip creation/modification when receiving signup changes.
"""
from __future__ import unicode_literals

from django.core.exceptions import ObjectDoesNotExist
from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.db.models.signals import pre_save, post_save
from django.db.models.signals import pre_delete, post_delete
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from ws.models import SignUp, WaitList, WaitListSignup, Trip
from ws.signup_utils import trip_or_wait, update_signup_queues
from ws.dateutils import local_now


@receiver(post_save, sender=SignUp)
def new_fcfs_signup(sender, instance, created, raw, using, update_fields, **kwargs):
    """ Handles first-come, first-serve signups:

        When a participant tries to sign up, put them on the trip, or its waiting list.
    """
    if created:
        trip_or_wait(instance)


@receiver(post_save, sender=Trip)
def changed_trip_size(sender, instance, created, raw, using, update_fields, **kwargs):
    if not created:
        update_signup_queues(instance)


@receiver(pre_delete, sender=Trip)
def empty_waitlist(sender, instance, using, **kwargs):
    """ Before emptying a Trip, empty the waitlist.

    This is needed because `free_spot_on_trip` will be triggered as part of the
    trip deletion process. If signups on the trip are deleted with a waitlist
    present, members of the waitlist will be emailed saying they made it on the
    trip (only to see the trip removed).
    """
    try:
        for signup in instance.waitlist.signups.all():
            signup.delete()
    except ObjectDoesNotExist:  # Not all trips will have waitlists
        pass


@receiver(post_delete, sender=SignUp)
def free_spot_on_trip(sender, instance, using, **kwargs):
    """ When somebody drops off a trip, bump up the top waitlist signup.

    Only performs bumping if the trip date hasn't arrived (if a leader is
    making changes the day of a trip, it's safe to assume the waitlisted
    spot won't be pulled in in time). Similarly, this would not make
    room for future signups, as FCFS signups close at midnight before.

    This will be triggered when an entire trip is deleted. `empty_waitlist()`
    will ensure that nobody is emailed about a free spot when a trip is
    being deleted.
    """
    if local_now().date() >= instance.trip.trip_date:
        return
    if instance.on_trip and instance.trip.algorithm == 'fcfs':
        trip = instance.trip
        first_signup = trip.waitlist.signups.first()
        if not first_signup:  # Empty waiting list, no need to open
            return
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
    leaders = ', '.join(unicode(leader) for leader in trip.leaders.all())
    msg = "You're leading '{}' with {} on {}.".format(trip_link, leaders, trip.trip_date)
    send_mail("You're a leader on {}".format(trip),
              # TODO: What information should be contained in this message?
              msg,
              trip.creator.participant.email,
              [leader.participant.email],
              fail_silently=True)
