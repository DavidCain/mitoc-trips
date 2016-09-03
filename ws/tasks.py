from __future__ import absolute_import

from celery import shared_task
from ws.utils import member_sheets
from ws import models


@shared_task
def update_discount_sheets():
    for discount in models.Discount.objects.all():
        member_sheets.update_discount_sheet(discount)
