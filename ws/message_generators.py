"""
Functions that take a request, create messages if applicable.
"""

from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.utils import timezone

from ws import models


def warn_if_needs_update(request):
    """ Create message if Participant info needs update. Otherwise, do nothing. """
    if not request.user.is_authenticated():
        return

    try:
        participant = request.user.participant
    except ObjectDoesNotExist:  # Authenticated, but no info yet
        msg = 'Personal information missing.'
    else:
        if participant.info_current:  # Record exists, is up to date
            return
        msg = 'Personal information is out of date.'

    msg += ' <a href="{}">Please update!</a>'.format(reverse('update_info'))
    messages.add_message(request, messages.WARNING, msg, extra_tags='safe')


def complain_if_missing_feedback(request):
    """ Create message if a Leader should supply feedback. """
    if not request.user.is_authenticated():
        return

    try:
        leader = request.user.participant.leader
    except ObjectDoesNotExist:
        return

    past_trips = leader.trip_set.filter(trip_date__lt=timezone.now().date())
    past_with_participants = [trip for trip in past_trips if
                              trip.signup_set.filter(on_trip=True).exists()]
    for trip in past_with_participants:
        trip_feedback = models.Feedback.objects.filter(leader=leader, trip=trip)
        if not trip_feedback.exists():
            trip_url = reverse('review_trip', args=(trip.id,))
            msg = ('Please supply feedback for '
                   '<a href="{}">{}</a>'.format(trip_url, trip))
            messages.add_message(request, messages.WARNING, msg, extra_tags='safe')
