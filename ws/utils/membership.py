from datetime import timedelta

from django.db.models import Q
from django.db.utils import OperationalError
from sentry_sdk import capture_exception

from ws import enums, models
from ws.utils import geardb
from ws.utils.dates import local_now


def refresh_all_membership_cache():
    """Refresh all membership caches in the system.

    After this is run, every participant in the system will have membership
    information that is no more than a week old.
    """
    last_week = local_now() - timedelta(weeks=1)
    needs_update = Q(membership__isnull=True) | Q(membership__last_cached__lt=last_week)

    all_participants = models.Participant.objects.select_related('membership')
    for par in all_participants.filter(needs_update):
        update_membership_cache(par)


def update_membership_cache(participant):
    """Use results from the gear database to update membership cache."""
    emails = geardb.verified_emails(participant.user)

    # If something is found, this method automatically updates the cache
    most_recent = geardb.membership_expiration(emails)

    # However, if nothing is found, we'll need to set that ourselves
    if not most_recent['membership']['email']:
        participant.update_membership(membership_expires=None, waiver_expires=None)


def reasons_cannot_attend(user, trip):
    """Yield reasons why the user is not allowed to attend the trip.

    Their cached membership may be sufficient to show that the last
    membership/waiver stored allows them to go on the trip. Otherwise, we
    must consult the gear database to be sure whether or not they can go.
    """
    if not user.is_authenticated:
        yield enums.TripIneligibilityReason.NOT_LOGGED_IN
        return

    participant = models.Participant.from_user(user, True)
    if not participant:
        yield enums.TripIneligibilityReason.NO_PROFILE_INFO
        return

    reasons = list(participant.reasons_cannot_attend(trip))
    if not any(reason.related_to_membership for reason in reasons):
        # There may be no reasons, or they may just not pertain to membership.
        # In either case, we don't need to refresh membership!
        yield from iter(reasons)
        return

    # The first check identified that the participant cannot attend due to membership problems
    # It used the cache, so some reasons for failure may have been due to a stale cache.
    # To be sure they can't attend, we must consult the gear database
    membership = participant.membership
    before_refreshing_ts = local_now()
    original_ts = membership.last_cached if membership else before_refreshing_ts

    try:
        update_membership_cache(participant)
    except OperationalError:
        capture_exception()
        return

    participant.membership.refresh_from_db()

    # (When running tests we often mock away wall time so it's constant)
    if local_now() != before_refreshing_ts:
        assert participant.membership.last_cached > original_ts

    yield from participant.reasons_cannot_attend(trip)
