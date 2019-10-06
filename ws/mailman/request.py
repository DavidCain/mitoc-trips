import logging
from typing import Iterable, Union

import requests
from django.contrib.auth.models import AnonymousUser, User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ws import models
from ws.mailman import api

logger = logging.getLogger(__name__)


@transaction.atomic(durable=True)  # Prevent nesting to guarantee commit
def process_request(request: models.MailingListRequest) -> None:
    """Process a single mailing list unsubscribe request.

    Uses database locking on the row to prevent duplicate requests.
    """
    assert request.action == models.MailingListRequest.Action.UNSUBSCRIBE.value

    request = models.MailingListRequest.objects.select_for_update().get(pk=request.pk)
    if not request.is_actionable:  # Some other transaction finished it first.
        return

    State = models.MailingListRequest.State
    try:
        resp = api.unsubscribe(request.email, request.mailing_list)
    except requests.ConnectionError:
        request.state = State.FAILED_RETRYABLE
    except Exception:  # pylint: disable=broad-except
        logger.exception("Unexpected exception unsubscribing %d", request.pk)
        request.state = State.FAILED_RETRYABLE

    request.last_time_attempted = timezone.now()
    request.num_attempts += 1

    if resp.status_code == 404:
        request.state = State.FAILED
    elif resp.status_code == 200:
        request.state = State.SUCCEEDED
    else:  # Who knows what's going on here. But try again later?
        request.state = State.FAILED_RETRYABLE

    if request.num_attempts > 3 and request.state != State.SUCCEEDED:
        logger.error("Giving up on unsubscribe attempt %d", request.pk)
        request.state = State.FAILED

    request.save()


def write_requests_to_db(
    email: str,
    mailing_lists: Iterable[str],
    requested_by: Union[User, AnonymousUser],
):
    State = models.MailingListRequest.State

    # TODO: Strongly consider adding rate limiting (cannot submit *new* unsub requests)

    mailing_list_requests = [
        models.MailingListRequest(
            requested_by_id=requested_by.pk if requested_by.is_authenticated else None,
            action=models.MailingListRequest.Action.UNSUBSCRIBE,
            email=email,
            mailing_list=mailing_list,
        )
        for mailing_list in mailing_lists
    ]

    with transaction.atomic():
        # Abort any old requests so we can replace them with new ones.
        # This avoids integrity errors on unique index - "one actionable request per list/email"
        # (And the lock from our `UPDATE` ensures that none were in progress)
        models.MailingListRequest.objects.filter(
            email=email,
            mailing_list__in={req.mailing_list for req in mailing_list_requests},
        ).filter(Q(state=State.REQUESTED) | Q(state=State.FAILED_RETRYABLE)).update(
            state=State.CANCELED
        )

        # TODO: Conflicts here are still possible!
        models.MailingListRequest.objects.bulk_create(mailing_list_requests)
