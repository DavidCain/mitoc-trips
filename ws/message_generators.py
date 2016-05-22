from __future__ import unicode_literals
"""
Functions that take a request, create messages if applicable.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.messages import INFO, WARNING
from django.core.urlresolvers import reverse
from django.utils import timezone

from ws.dateutils import local_now, is_winter_school
from ws import models
from ws import perm_utils


class LotteryMessages(object):
    """ Supply messages relating to lottery status of one participant. """
    WARN_AFTER_DAYS_OLD = 5  # After these days, remind of lottery status

    def __init__(self, request):
        self.request = request

    @property
    def lotteryinfo(self):
        return self.request.participant and self.participant.lotteryinfo

    def supply_all_messages(self):
        if not self.request.participant or not is_winter_school():
            return
        self.warn_if_missing_lottery()

        if self.lotteryinfo:  # (warnings are redundant if no lottery info)
            self.warn_if_no_ranked_trips()
            self.warn_if_dated_info()

    def prefs_link(self, text='lottery preferences'):
        # Remember to set extra_tags='safe' to avoid escaping HTML
        return '<a href="{}">{}</a>'.format(reverse('trip_preferences'), text)

    def warn_if_missing_lottery(self):
        """ Warn if lottery information isn't found for the participant.

        Because car information and ranked trips are submitted in one form,
        checking participant.lotteryinfo is sufficient to check both.
        """
        if not self.lotteryinfo:
            msg = "You haven't set your {}.".format(self.prefs_link())
            messages.add_message(self.request, WARNING, msg, extra_tags='safe')

    def warn_if_no_ranked_trips(self):
        """ Warn the user if there are future signups, and none are ranked. """
        today = local_now().date()
        manager = models.SignUp.objects
        future_signups = manager.filter(participant=self.request.participant,
                                        trip__trip_date__gte=today)
        some_trips_ranked = future_signups.filter(order__isnull=False).count()
        if future_signups.count() > 1 and not some_trips_ranked:
            msg = "You haven't " + self.prefs_link("ranked upcoming trips.")
            messages.add_message(self.request, WARNING, msg, extra_tags='safe')

    def warn_if_dated_info(self):
        """ If the participant hasn't updated information in a while, remind
        them of their status as a driver. """
        if self.lotteryinfo:
            timedelta = timezone.now() - self.lotteryinfo.last_updated
            days_old = timedelta.days

            if days_old >= self.WARN_AFTER_DAYS_OLD:
                msg = ("You haven't updated your {} in {} days. "
                       "You will be counted as a {}driver in the next lottery.")
                driver_prefix = "" if self.lotteryinfo.is_driver else "non-"
                msg = msg.format(self.prefs_link(), days_old, driver_prefix)
                messages.add_message(self.request, INFO, msg, extra_tags='safe')


def warn_if_needs_update(request):
    """ Create message if Participant info needs update. Otherwise, do nothing. """
    if not request.user.is_authenticated():
        return

    participant = request.participant
    if not participant:  # Authenticated, but no info yet
        msg = 'Personal information missing.'
    else:
        if participant.info_current:  # Record exists, is up to date
            return
        msg = 'Personal information is out of date.'

    msg += ' <a href="{}">Update</a> to sign up for trips'.format(reverse('update_info'))
    messages.add_message(request, WARNING, msg, extra_tags='safe')


def _feedback_eligible_trips(participant):
    """ Recent completed trips where participants were not given feedback. """
    today = local_now().date()
    one_month_ago = today - timedelta(days=30)
    recent_trips = participant.trips_led.filter(trip_date__lt=today,
                                                trip_date__gt=one_month_ago)
    return recent_trips.filter(signup__on_trip=True).distinct()


def complain_if_missing_feedback(request):
    """ Create message if a Leader should supply feedback. """
    if not perm_utils.is_leader(request.user):
        return

    participant = request.participant

    # TODO: Could be made more efficient- O(n) queries, where n= number of trips
    for trip in _feedback_eligible_trips(participant):
        trip_feedback = models.Feedback.objects.filter(leader=participant, trip=trip)
        if not trip_feedback.exists():
            trip_url = reverse('review_trip', args=(trip.id,))
            msg = ('Please supply feedback for '
                   '<a href="{}">{}</a>'.format(trip_url, trip))
            messages.add_message(request, WARNING, msg, extra_tags='safe')
