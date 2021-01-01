import inspect
import logging
from contextlib import contextmanager
from datetime import timedelta
from functools import wraps

from celery import group, shared_task
from celery.five import monotonic  # pylint: disable=no-name-in-module
from django.core.cache import cache

from ws import cleanup, models, settings
from ws.email.sole import send_email_to_funds
from ws.email.trips import send_trips_summary
from ws.lottery.run import SingleTripLotteryRunner, WinterSchoolLotteryRunner
from ws.utils import dates as date_utils
from ws.utils import geardb, member_sheets

logger = logging.getLogger(__name__)

LOCK_EXPIRE = 10 * 60  # ten minutes


@contextmanager
def exclusive_lock(task_identifier):
    """ Obtain an exclusively lock, using the task_identifier as a unique ID.

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
    """ Wraps a task that must be executed only once.

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
    """ Lock the sheet and add/update a single participant.

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
            "Google Sheets functionality is disabled, not updating " "'%s' for %s",
            discount.name,
            participant.name,
        )
        return

    member_sheets.update_participant(discount, participant)


@mutex_task('update_discount-{discount_id}')
def update_discount_sheet(discount_id):
    """ Overwrite the sheet to include all members desiring the discount.

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
            "Google Sheets functionality is disabled, " "not updating sheet for '%s'",
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


@shared_task  # Harmless if we run it twice
def update_participant_affiliation(participant_id):
    """ Use the participant's affiliation to update the gear database. """
    participant = models.Participant.objects.get(pk=participant_id)
    geardb.update_affiliation(participant)


@mutex_task()
def send_trip_summaries_email():
    """ Email summary of upcoming trips to mitoc-trip-announce@mit.edu """
    send_trips_summary()


@mutex_task()
def send_sole_itineraries():
    """ Email trip itineraries to Student Organizations, Leadership and Engagement.

    This task should be run daily, so that it will always send SOLE
    this information _before_ the trip actually starts.
    """
    tomorrow = date_utils.local_date() + timedelta(days=1)
    trips = models.Trip.objects.filter(trip_date=tomorrow, info__isnull=False)
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
    """ Purge non-students from student-only discounts. """
    logger.info("Purging non-students from student-only discounts")
    cleanup.purge_non_student_discounts()


@mutex_task()
def purge_old_medical_data():
    """ Purge old, dated medical information. """
    logger.info("Purging outdated medical information")
    cleanup.purge_old_medical_data()


@mutex_task('single_trip_lottery-{trip_id}')
def run_lottery(trip_id, lottery_config=None):
    """ Run a lottery algorithm for the given trip (idempotent).

    If running on a trip that isn't in lottery mode, this won't make
    any changes (making this task idempotent).
    """
    logger.info("Running lottery for trip #%d", trip_id)
    trip = models.Trip.objects.get(pk=trip_id)
    runner = SingleTripLotteryRunner(trip)
    runner()
