"""Handle aspects of trip creation/modification when receiving signup changes."""
# Signals are a terrible pattern that I aim to replace eventually.
# Ruff will complain about the large number of arguments. We can ignore for now.
# ruff: noqa: PLR0913
import contextlib
import logging

from django.db.models.signals import (
    m2m_changed,
    post_delete,
    post_save,
    pre_delete,
    pre_save,
)
from django.dispatch import receiver
from kombu.exceptions import OperationalError

from ws import enums, tasks
from ws.celery_config import app
from ws.models import LeaderSignUp, SignUp, Trip, WaitList
from ws.utils.signups import trip_or_wait, update_queues_if_trip_open

logger = logging.getLogger(__name__)


@receiver(post_save, sender=SignUp)
def new_fcfs_signup(sender, instance, created, raw, using, update_fields, **kwargs):
    """Handles first-come, first-serve signups:

    When a participant tries to sign up, put them on the trip, or its waiting list.
    """
    if created and not getattr(instance, "skip_signals", False):
        trip_or_wait(instance)


@receiver(pre_delete, sender=Trip)
def empty_waitlist(sender, instance, using, **kwargs):
    """Before emptying a Trip, empty the waitlist.

    This is needed because `free_spot_on_trip` will be triggered as part of the
    trip deletion process. If signups on the trip are deleted with a waitlist
    present, members of the waitlist will be emailed saying they made it on the
    trip (only to see the trip removed).
    """
    with contextlib.suppress(WaitList.DoesNotExist):
        instance.waitlist.signups.delete()


@receiver(post_delete, sender=SignUp)
def free_spot_on_trip(sender, instance, using, **kwargs):
    """When a participant deletes a signup, update queues if applicable."""
    if not getattr(instance, "skip_signals", False):
        update_queues_if_trip_open(instance.trip)


@receiver(post_save, sender=LeaderSignUp)
def leader_signup(sender, instance, created, raw, using, update_fields, **kwargs):
    """Add the leader to the trip's list of leaders, decrement available spots."""
    trip = instance.trip
    if created and trip.maximum_participants > 0 and trip.signups_not_yet_open:
        trip.maximum_participants -= 1
        trip.save()
    trip.leaders.add(instance.participant)


@receiver(post_save, sender=Trip)
def add_waitlist(sender, instance, created, raw, using, update_fields, **kwargs):
    if created:
        instance.waitlist = WaitList.objects.create(trip=instance)
        instance.save()


@receiver(m2m_changed, sender=Trip.leaders.through)
def delete_leader_signups(
    sender, instance, action, reverse, model, pk_set, using, **kwargs
):
    """When removing leaders from the trip, delete their signups.

    Ideally, we should be able to use the pre_remove signal to detect which
    leaders in particular were removed. However, the pre_remove signal isn't
    set at all (instead, the whole M2M is cleared and reset).
    See this issue for more: https://code.djangoproject.com/ticket/6707

    The issue was solved in Django 1.9, so this is a hack until we upgrade.
    """
    # Signal order: pre_clear, post_clear, pre_add, post_add, [completed]
    if action == "post_add":
        leaders = instance.leaders.all()
        instance.leadersignup_set.exclude(participant__in=leaders).delete()


@receiver(pre_save, sender=Trip)
def revoke_existing_task(sender, instance, raw, using, update_fields, **kwargs):
    """If updating a trip, revoke any existing lottery task.

    First-come, first-serve trips don't need a lottery task, and changing
    the lottery time must result in a new scheduled lottery time.

    If we're revoking the task due to changing lottery times,
    `add_lottery_task` will ensure that new task is scheduled.
    """
    try:
        trip = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:  # New trip, initiated with no task
        return

    # TODO: There's a race condition here; we should lock `trip` exclusively
    new_close_time = instance.signups_close_at != trip.signups_close_at
    needs_revoke = new_close_time or trip.algorithm != "lottery"
    if trip.lottery_task_id and needs_revoke:
        try:
            app.control.revoke(trip.lottery_task_id)
        except OperationalError:
            # Log the exception, but don't raise exceptions, preventing trip saving
            logger.exception("Failed to revoke lottery task for trip %s", trip.pk)
        else:
            instance.lottery_task_id = None


@receiver(post_save, sender=Trip)
def add_lottery_task(sender, instance, created, raw, using, update_fields, **kwargs):
    """Add a task to execute the lottery at the time the trip closes.

    If the signups close at some point in the past, this will result in the
    lottery being executed immediately.
    """
    trip = instance

    if trip.program_enum == enums.Program.WINTER_SCHOOL:
        return  # Winter School lotteries are handled separately
    if trip.lottery_task_id or trip.algorithm != "lottery":
        return  # Only new lottery trips get a new task

    try:
        task_id = tasks.run_lottery.apply_async((trip.pk,), eta=trip.signups_close_at)
    except OperationalError:
        logger.exception("Failed to make lottery task for trip %s", trip.pk)
    else:
        trip.lottery_task_id = task_id
        # Use update() to avoid repeated signal on post_save
        sender.objects.filter(pk=trip.pk).update(lottery_task_id=task_id)


@receiver(pre_delete, sender=Trip)
def revoke_lottery_task(sender, instance, using, **kwargs):
    """Before deleting a Trip, de-schedule the lottery task."""
    if instance.lottery_task_id:
        app.control.revoke(instance.lottery_task_id)
