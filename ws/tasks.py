from __future__ import absolute_import

import random

from celery import group, shared_task
from django.core.cache import cache

from ws import models
from ws.utils import member_sheets


def acquire_lock(discount, lock_expires_after=300):
    """ Generate a lock on the discount's Google sheet.

    Because cache adds are an atomic operation, we can use this
    to create a lock (that will automatically expire if not unset).
    Returns True if the key was added, False if already present.
    """
    return cache.add(discount.ga_key, 'true', lock_expires_after)


def release_lock(discount):
    """ Mark the sheet as updated and free to be locked by another task. """
    return cache.delete(discount.ga_key)


def increasing_retry(num_retries):
    """ Returning an increasing countdown (in seconds).

    Includes randomness to avoid the Thundering Herd Problem.
    """
    return int(random.uniform(2, 4) ** num_retries)


@shared_task(bind=True, max_retries=4)
def update_discount_sheet(self, discount_id):
    """ Overwrite the sheet to include all members desiring the discount.

    This is the only means of removing users if they no longer
    wish to share their information, so it should be run periodically.
    """
    discount = models.Discount.objects.get(pk=discount_id)
    if acquire_lock(discount):
        try:
            member_sheets.update_discount_sheet(discount)
        finally:
            release_lock(discount)
    else:
        self.retry(countdown=increasing_retry(self.request.retries))


@shared_task
def update_all_discount_sheets():
    discount_pks = models.Discount.objects.values_list('pk', flat=True)
    group([update_discount_sheet.s(pk) for pk in discount_pks])()


@shared_task(bind=True, max_retries=4)
def update_participant(self, discount_id, participant_id):
    """ Lock the sheet and add/update a single participant. """
    discount = models.Discount.objects.get(pk=discount_id)
    participant = models.Participant.objects.get(pk=participant_id)

    if acquire_lock(discount):
        try:
            member_sheets.update_participant(discount, participant)
        finally:
            release_lock(discount)
    else:
        self.retry(countdown=increasing_retry(self.request.retries))
