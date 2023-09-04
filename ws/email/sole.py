import logging
from typing import TYPE_CHECKING

from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template

from ws.settings import BURSAR_NAME
from ws.utils import itinerary

if TYPE_CHECKING:
    from ws import models

logger = logging.getLogger(__name__)


def send_email_to_funds(trip: 'models.Trip') -> None:
    """Register the trip with SOLE for insurance & liability reasons.

    This automated email is taking the place of SOLE's Student Travel Form.

    For optimum efficiency, the `trip` should prefetch 'leaders' and select 'info'.
    """
    on_trip = trip.signup_set.filter(on_trip=True).select_related('participant')
    context = {
        'trip': trip,
        'signups_on_trip': on_trip,
        'cars': itinerary.get_cars(trip),
        'bursar_name': BURSAR_NAME,
    }

    text_content = get_template('email/sole/funds_email.txt').render(context)
    html_content = get_template('email/sole/funds_email.html').render(context)

    subject = f"MITOC-Trips registration: {trip.name}"
    bursar = 'mitoc-bursar@mit.edu'
    recipients = [
        'sole-desk@mit.edu',
        'paulmurp@mit.edu',  # Associate Dean of SOLE, https://studentlife.mit.edu/sole/meet-staff
    ]
    msg = EmailMultiAlternatives(
        subject,
        text_content,
        to=recipients,
        cc=[bursar],
        reply_to=[bursar],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()
    logger.info("Sent itinerary for trip #%d to %s, CCing %s", trip.pk, msg.to, msg.cc)
