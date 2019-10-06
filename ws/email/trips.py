from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template

import ws.utils.dates as dateutils
from ws import models
from ws.templatetags.trip_tags import annotated_for_trip_list


def _eligible_trips():
    """ Identify all trips that are open for signups, or will be. """
    now = dateutils.local_now()

    upcoming_trips = (
        models.Trip.objects.filter(trip_date__gte=now.date())
        .filter(signups_close_at__gt=now)
        .order_by('trip_date', 'time_created')
    )

    return annotated_for_trip_list(upcoming_trips)


def _trips_to_summarize():
    """ Return trips which should be summarized in the email message.

    Returns trips broken up into two different classifications:
    - Trips that are currently open for signup
    - Trips that are not yet open for signup, but will be soon
    """
    open_for_signup = []
    not_yet_open = []
    for trip in _eligible_trips():
        if trip.signups_open:
            open_for_signup.append(trip)
        else:
            assert trip.signups_not_yet_open
            not_yet_open.append(trip)
    return (open_for_signup, not_yet_open)


def send_trips_summary(recipient='mitoc-trip-announce@mit.edu'):
    """ Send a weekly blast of upcoming trips! """
    open_for_signup, not_yet_open = _trips_to_summarize()
    if not (open_for_signup or not_yet_open):
        return  # No need to send empty email
    context = {'open_for_signup': open_for_signup, 'not_yet_open': not_yet_open}

    text = get_template('email/trips/upcoming_trips.txt').render(context).strip()
    html = get_template('email/trips/upcoming_trips.html').render(context)

    subject = f"MITOC Trips | {len(open_for_signup)} currently open, {len(not_yet_open)} upcoming"
    msg = EmailMultiAlternatives(subject, text, to=[recipient])
    msg.attach_alternative(html, "text/html")
    msg.send()
