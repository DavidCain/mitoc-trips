import inspect
import logging
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps
from time import monotonic

import requests
from celery import group, shared_task
from django.core.cache import cache
from django.db import transaction

from ws import cleanup, models, settings
from ws.email import renew
from ws.email.sole import send_email_to_funds
from ws.email.trips import send_trips_summary
from ws.lottery.run import SingleTripLotteryRunner, WinterSchoolLotteryRunner
from ws.utils import dates as date_utils
from ws.utils import geardb, member_sheets

logger = logging.getLogger(__name__)

LOCK_EXPIRE = 10 * 60  # ten minutes


@contextmanager
def exclusive_lock(task_identifier):
    """Obtain an exclusively lock, using the task_identifier as a unique ID.

    This helps prevents the case of multiple workers executing the same task at
    the same time, which can cause unexpected side effects.
    """
    # See: https://celery.readthedocs.io/en/latest/tutorials/task-cookbook.html

    # Plan to timeout a few seconds before the limit
    # (After `LOCK_EXPIRE` seconds have passed, the cache will self-clean)
    timeout_at = monotonic() + LOCK_EXPIRE - 3

    # Try to add the value to the cache.
    # Returns False if already cached (another worker added it already)
    # Returns True otherwise (this worker is the first to add the key)
    got_lock = cache.add(task_identifier, 'true', LOCK_EXPIRE)

    # Yield our ability to obtain a lock, but always cleanup
    try:
        yield got_lock
    finally:
        # If `got_lock` was False, we don't own the lock - never clean up
        # If we're close to the timeout, just let the cache self-clean
        if got_lock and monotonic() < timeout_at:
            cache.delete(task_identifier)


def mutex_task(task_id_template=None, **shared_task_kwargs):
    """Wraps a task that must be executed only once.

    :param task_id_template: String that makes unique task IDs from passed args
        (If omitted, we just use the function name)
    :param shared_task_kwargs: Passed through to `shared_task`
    """

    def decorator(func):
        signature = inspect.signature(func)

        @shared_task(**shared_task_kwargs, bind=True)
        @wraps(func)
        def wrapped_task(self, *task_args, **task_kwargs):
            if task_id_template:
                passed_args = signature.bind(*task_args, **task_kwargs)
                passed_args.apply_defaults()
                task_identifier = task_id_template.format_map(passed_args.arguments)
            else:
                task_identifier = func.__name__

            with exclusive_lock(task_identifier) as has_lock:
                if has_lock:
                    return func(*task_args, **task_kwargs)
                logger.debug("Other worker already processing %s", task_identifier)
            return None

        return wrapped_task

    return decorator


@mutex_task('update_discount-{discount_id}')
def update_discount_sheet_for_participant(discount_id: int, participant_id: int):
    """Lock the sheet and add/update a single participant.

    This task should not run at the same time that we're updating the sheet for
    another participant (or for all participants, as we do nightly).
    """
    discount = models.Discount.objects.get(pk=discount_id)
    if not discount.ga_key:
        # Form logic should prevent ever letting participants "enroll" in this type of discount
        logger.error("Discount %s does not have a Google Sheet!", discount.name)
        return

    participant = models.Participant.objects.get(pk=participant_id)

    if settings.DISABLE_GSHEETS:
        logger.warning(
            "Google Sheets functionality is disabled, not updating '%s' for %s",
            discount.name,
            participant.name,
        )
        return

    member_sheets.update_participant(discount, participant)


@mutex_task('update_discount-{discount_id}')
def update_discount_sheet(discount_id):
    """Overwrite the sheet to include all members desiring the discount.

    This is the only means of removing users if they no longer
    wish to share their information, so it should be run periodically.

    This task should not run at the same time that we're updating the sheet for
    another participant (or for all participants, as we do nightly).
    """
    discount = models.Discount.objects.get(pk=discount_id)
    if not discount.ga_key:
        # Form logic should prevent ever letting participants "enroll" in this type of discount
        logger.error("Discount %s does not have a Google Sheet!", discount.name)
        return

    logger.info("Updating the discount sheet for %s", discount.name)

    if settings.DISABLE_GSHEETS:
        logger.warning(
            "Google Sheets functionality is disabled, not updating sheet for '%s'",
            discount.name,
        )
        return

    member_sheets.update_discount_sheet(discount)


@mutex_task()
def update_all_discount_sheets():
    logger.info("Updating the member roster for all discount sheets")
    discount_pks = models.Discount.objects.exclude(ga_key='').values_list(
        'pk', flat=True
    )
    group([update_discount_sheet.s(pk) for pk in discount_pks])()


@shared_task(
    auto_retry_for=(requests.exceptions.HTTPError,),
    # Account for brief outages by retrying after 1 minute, then 2, then 4, then 8
    retry_backoff=60,
    max_retries=4,
)
def update_participant_affiliation(participant_id: int):
    """Use the participant's affiliation to update the gear database."""
    participant = models.Participant.objects.get(pk=participant_id)
    response = geardb.update_affiliation(participant)
    if response:  # `None` implies nothing to do
        response.raise_for_status()


@shared_task  # Locking done at db level to ensure idempotency
def remind_lapsed_participant_to_renew(participant_id: int):
    """A task which should only be called by `remind_participants_to_renew'.

    Like its parent task, is designed to be idempotent (so we only notify
    participants once per year).
    """
    participant = models.Participant.objects.get(pk=participant_id)

    # It's technically possible that the participant opted out in between execution
    if not participant.send_membership_reminder:
        logger.info("Not reminding participant %s, who since opted out", participant.pk)
        return

    now = date_utils.local_now()
    with transaction.atomic():
        (reminder, created) = (
            models.MembershipReminder.objects
            # Make sure we get an exclusive lock to prevent sending a redundant email.
            .select_for_update()
            # It's possible this is the first reminder! If so, create it now.
            # (the unique constraint on participant will ensure other queries can't insert
            .get_or_create(
                participant=participant,
                defaults={'reminder_sent_at': now},
            )
        )

        if not created:
            logger.info("Last reminded %s: %s", participant, reminder.reminder_sent_at)
            # Reminders should be sent ~40 days before the participant's membership has expired.
            # We should only send one reminder every ~365 days or so.
            # Pick 300 days as a sanity check that we send one message yearly (+/- some days)
            if reminder.reminder_sent_at > (now - timedelta(days=300)):
                raise ValueError(f"Mistakenly trying to notify {participant} to renew")

        # (Note that this method makes some final assertions before delivering)
        # If the email succeeds, we'll commit the reminder record (else rollback)
        renew.send_email_reminding_to_renew(participant)


@shared_task  # Locking done at db level to ensure idempotency
def remind_participants_to_renew():
    """Identify all participants who requested membership reminders, email them.

    This method is designed to be idempotent (one email per participant).
    """
    now = date_utils.local_now()

    # Reminders should be sent ~40 days before the participant's membership has expired.
    # We should only send one reminder every ~365 days or so.
    most_recent_allowed_reminder_time = now - timedelta(days=300)

    participants_needing_reminder = models.Participant.objects.filter(
        # Crucially, we *only* send these reminders to those who've opted in.
        send_membership_reminder=True,
        # Anybody with soon-expiring membership is eligible to renew.
        membership__membership_expires__lte=(
            now + models.Membership.RENEWAL_WINDOW
        ).date(),
        # While it should technically be okay to tell people to renew *after* expiry, don't.
        # We'll run this task daily, targeting each participant for ~40 days before expiry.
        # Accordingly, various edge cases should have been handled some time in those 40 days.
        # The language in emails will suggest that renewal is for an active membership, too.
        membership__membership_expires__gte=now.date(),
    ).exclude(
        # Don't attempt to remind anybody who has already been reminded.
        membershipreminder__reminder_sent_at__gte=most_recent_allowed_reminder_time
    )

    # Farm out the delivery of individual emails to separate workers.
    for pk in participants_needing_reminder.values_list('pk', flat=True):
        logger.info("Identified participant %d as needing renewal reminder", pk)
        remind_lapsed_participant_to_renew.delay(pk)


@mutex_task()
def send_trip_summaries_email():
    """Email summary of upcoming trips to mitoc-trip-announce@mit.edu"""
    send_trips_summary()


@mutex_task()
def send_sole_itineraries():
    """Email trip itineraries to Student Organizations, Leadership and Engagement.

    This task should be run daily, so that it will always send SOLE
    this information _before_ the trip actually starts.
    """
    # TODO: Make this task idempotent, by actually logging when emails were sent
    tomorrow = date_utils.local_date() + timedelta(days=1)
    trips = models.Trip.objects.filter(trip_date=tomorrow)
    logger.info(
        "Sending itineraries for %d trips taking place tomorrow, %s",
        trips.count(),
        tomorrow,
    )
    for trip in trips.select_related('info').prefetch_related('leaders'):
        send_email_to_funds(trip)


@mutex_task()
def run_ws_lottery():
    logger.info("Commencing Winter School lottery run")
    runner = WinterSchoolLotteryRunner()
    runner()


@mutex_task()
def purge_non_student_discounts():
    """Purge non-students from student-only discounts."""
    logger.info("Purging non-students from student-only discounts")
    cleanup.purge_non_student_discounts()


@mutex_task()
def purge_old_medical_data():
    """Purge old, dated medical information."""
    logger.info("Purging outdated medical information")
    cleanup.purge_old_medical_data()


@mutex_task('single_trip_lottery-{trip_id}')
def run_lottery(trip_id, lottery_config=None):
    """Run a lottery algorithm for the given trip (idempotent).

    If running on a trip that isn't in lottery mode, this won't make
    any changes (making this task idempotent).
    """
    logger.info("Running lottery for trip #%d", trip_id)
    trip = models.Trip.objects.get(pk=trip_id)
    runner = SingleTripLotteryRunner(trip)
    runner()
