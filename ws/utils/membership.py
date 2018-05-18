from django.db.utils import OperationalError

from ws import models
from ws import sentry
from ws.utils.dates import local_now
from ws.utils.geardb import membership_expiration, verified_emails


def update_membership_cache(participant):
    """ Use results from the gear database to update membership cache. """
    # If something is found, this method automatically updates the cache
    most_recent = membership_expiration(verified_emails(participant.user))

    # However, if nothing is found, we'll need to set that ourselves
    if not most_recent['membership']['email']:
        participant.update_membership(membership_expires=None,
                                      waiver_expires=None)


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
        if sentry.client:
            sentry.client.captureException()
        return True  # Database is down! Just assume they can attend

    participant.membership.refresh_from_db()

    assert participant.membership.last_cached > original_ts

    return participant.can_attend(trip)
