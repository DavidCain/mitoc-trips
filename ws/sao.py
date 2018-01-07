from django.core.mail import EmailMultiAlternatives
from django.template import Context
from django.template.loader import get_template

from ws.utils import itinerary


def send_email_to_funds(trip, recipient='funds@mit.edu'):
    """ Register the trip with SAO for insurance & liability reasons.

    This automated email is taking the place of SAO's Student Travel Form.

    For optimum efficiency, the `trip` should prefetch 'leaders' and select 'info'.
    """
    on_trip = trip.signup_set.filter(on_trip=True).select_related('participant')
    context = Context({
        'trip': trip,
        'signups_on_trip': on_trip,
        'cars': itinerary.get_cars(trip)
    })

    text_content = get_template('sao/funds_email.txt').render(context)
    html_content = get_template('sao/funds_email.html').render(context)

    subject = "MITOC-Trips registration: {}".format(trip.name)
    msg = EmailMultiAlternatives(subject, text_content, to=[recipient])
    msg.attach_alternative(html_content, "text/html")
    msg.send()
