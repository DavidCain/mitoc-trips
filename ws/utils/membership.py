from datetime import timedelta

from django.db.models import Q
from django.db.utils import OperationalError
from sentry_sdk import capture_exception

from ws import models
from ws.utils.dates import local_now
from ws.utils.geardb import membership_expiration, verified_emails


def refresh_all_membership_cache():
    """ Refresh all membership caches in the system.

    After this is run, every participant in the system will have membership
    information that is no more than a week old.
    """
    last_week = local_now() - timedelta(weeks=1)
    needs_update = Q(membership__isnull=True) | Q(membership__last_cached__lt=last_week)

    all_participants = models.Participant.objects.select_related('membership')
    for par in all_participants.filter(needs_update):
        update_membership_cache(par)


def update_membership_cache(participant):
    """ Use results from the gear database to update membership cache. """
    # If something is found, this method automatically updates the cache
    most_recent = membership_expiration(verified_emails(participant.user))

    # However, if nothing is found, we'll need to set that ourselves
    if not most_recent['membership']['email']:
        participant.update_membership(membership_expires=None, waiver_expires=None)


def can_attend_trip(user, trip):
    """ Return whether the user's membership allows them to attend the trip.

    Their cached membership may be sufficient to show that the last
    membership/waiver stored allows them to go on the trip. Otherwise, we
    must consult the gear database to be sure whether or not they can go.
    """
    participant = models.Participant.from_user(user, True)
    if not participant:
        return False
    if participant.can_attend(trip):
        return True

    # The first check used the cache, but failed.
    # To be sure they can't attend, we must consult the gear database
    membership = participant.membership
    original_ts = membership.last_cached if membership else local_now()

    try:
        update_membership_cache(participant)
    except OperationalError:
        capture_exception()
        return True  # Database is down! Just assume they can attend

    participant.membership.refresh_from_db()

    assert participant.membership.last_cached > original_ts

    return participant.can_attend(trip)
