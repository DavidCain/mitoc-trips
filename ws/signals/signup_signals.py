"""
Handle aspects of trip creation/modification when receiving signup changes.
"""
from __future__ import unicode_literals

from django.core.mail import send_mail
from django.core.urlresolvers import reverse
from django.db.models.signals import post_save
from django.db.models.signals import pre_delete, post_delete
from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from ws.dateutils import local_now
from ws.models import SignUp, WaitList, WaitListSignup, Trip
from ws import signup_utils


@receiver(post_save, sender=SignUp)
def new_fcfs_signup(sender, instance, created, raw, using, update_fields, **kwargs):
    """ Handles first-come, first-serve signups:

        When a participant tries to sign up, put them on the trip, or its waiting list.
    """
    if created and not getattr(instance, 'skip_signals', False):
        signup_utils.trip_or_wait(instance)


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
    except WaitList.DoesNotExist:  # Not all trips will have waitlists
        pass


@receiver(post_delete, sender=SignUp)
def free_spot_on_trip(sender, instance, using, **kwargs):
    """ When a participant deletes a signup, update queues if applicable. """
    if not getattr(instance, 'skip_signals', False):
        signup_utils.update_queues_if_trip_open(instance.trip)


@receiver(post_save, sender=SignUp)
def on_trip_bump(sender, instance, created, raw, using, update_fields, **kwargs):
    """ When a signup is no longer on the trip, bump up any waitlist spots.

    Only performs bumping if the trip date hasn't arrived (if a leader is
    making changes the day of a trip, it's safe to assume the waitlisted
    spot won't be pulled in in time). Similarly, this would not make
    room for future signups, as FCFS signups close at midnight before.
    """
    if not instance.on_trip:
        signup_utils.update_queues_if_trip_open(instance.trip)


@receiver(post_delete, sender=WaitListSignup)
def bumped_from_waitlist(sender, instance, using, **kwargs):
    """ Notify previously waitlisted participants if they're on trip.

    If the trip happened in the past, it's safe to assume it's just the
    leader modifying the participant list. Don't notify in this case.

    When a waitlist signup is deleted, it generally means the participant
    is on the trip. The only other case is a complete trip deletion,
    or a manual signup deletion. In either case, these actions are only
    triggered by admins. Notifications will only be sent out if the
    corresponding signup is now on the trip.
    """
    wl_signup, signup = instance, instance.signup
    if getattr(signup, 'skip_signals', False):
        return

    if not wl_signup.signup.on_trip:
        return  # Could just be deleted, don't want to falsely notify
    trip = signup.trip
    if trip.trip_date < local_now().date():
        return  # Trip was yesterday or earlier, no point notifying
    trip_link = get_trip_link(trip)
    send_mail("You're signed up for {}".format(trip),
              "You're on {}! If you can't make it, please remove yourself "
              "from the trip so others can join.".format(trip_link),
              trip.creator.email,
              [signup.participant.email],
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
    relation (that is, at trip creation, or if a new leader is added).
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
              trip.creator.email,
              [leader.email],
              fail_silently=True)
