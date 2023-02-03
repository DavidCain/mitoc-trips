import logging
from datetime import timedelta

from django.core import mail
from django.template.loader import get_template

from ws import models, unsubscribe
from ws.utils import dates as date_utils

logger = logging.getLogger(__name__)


def send_email_reminding_to_renew(
    participant: models.Participant,
) -> mail.EmailMultiAlternatives:
    """Send a (one-time, will not be repeated) reminder when dues are nearly up.

    These emails are meant to be opt-in (i.e. participants must willingly *ask*
    to get reminders when it's time to renew).
    """
    par = f'{participant.email} ({participant.pk})'
    today = date_utils.local_date()

    membership: models.Membership | None = participant.membership

    # For (hopefully) obvious reasons, you *must* have an old membership to renew.
    # The trips database is *not* the source of truth for membership.
    # However, we very frequently query the gear database for membership status.
    if not (membership and membership.membership_expires):
        raise ValueError(f"Can't email {par} about renewal (no membership on file!)")

    # Language in our email assumes that the membership is still active.
    # Accordingly, never send a reminder if membership has expired already.
    if today > membership.membership_expires:
        raise ValueError(f"Membership has already expired for {par}")

    renewal_date = membership.date_when_renewal_is_recommended(report_past_dates=True)
    assert renewal_date is not None, "Should not recommend renewal for non-member!"

    # We should never remind people to renew before it's actually possible.
    if today < renewal_date:
        # (Buying a new membership today won't credit them the remaining days)
        raise ValueError(f"We don't yet recommend renewal for {par}")

    context = {
        'participant': participant,
        'discounts': participant.discounts.all().order_by('name'),
        'expiry_if_renewing': membership.membership_expires + timedelta(days=365),
        'unsubscribe_token': unsubscribe.generate_unsubscribe_token(participant),
    }
    text_content = get_template('email/membership/renew.txt').render(context)
    html_content = get_template('email/membership/renew.html').render(context)

    msg = mail.EmailMultiAlternatives(
        subject="[Action required] Renew your MITOC membership",
        body=text_content,
        to=[participant.email],
        reply_to=['mitoc-desk@mit.edu'],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()
    logger.info("Reminded %s to renew their membership", par)
    return msg
