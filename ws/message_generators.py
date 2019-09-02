"""
Functions that take a request, create messages if applicable.
"""
import logging
from datetime import timedelta

from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

import ws.utils.dates as dateutils
import ws.utils.perms
from ws import models

logger = logging.getLogger(__name__)


class LotteryMessages:
    """ Supply messages relating to lottery status of one participant. """

    WARN_AFTER_DAYS_OLD = 5  # After these days, remind of lottery status

    def __init__(self, request):
        self.request = request

    @property
    def lotteryinfo(self):
        participant = self.request.participant
        if not participant:
            return None

        try:
            return participant.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            return None

    def supply_all_messages(self):
        if not self.request.participant or not dateutils.is_winter_school():
            return
        self.warn_if_missing_lottery()
        self.warn_if_car_missing()

        if self.lotteryinfo:  # (warnings are redundant if no lottery info)
            self.warn_if_no_ranked_trips()
            self.warn_if_dated_info()

    @staticmethod
    def profile_link(text):
        # Remember to set extra_tags='safe' to avoid escaping HTML
        return '<a href="{}">{}</a>'.format(reverse('edit_profile'), text)

    @staticmethod
    def prefs_link(text='lottery preferences'):
        # Remember to set extra_tags='safe' to avoid escaping HTML
        return '<a href="{}">{}</a>'.format(reverse('lottery_preferences'), text)

    def warn_if_missing_lottery(self):
        """ Warn if lottery information isn't found for the participant.

        Because car information and ranked trips are submitted in one form,
        checking participant.lotteryinfo is sufficient to check both.
        """
        if not self.lotteryinfo:
            msg = "You haven't set your {}.".format(self.prefs_link())
            messages.warning(self.request, msg, extra_tags='safe')

    def warn_if_car_missing(self):
        lottery = self.lotteryinfo
        if not lottery:
            return
        if lottery.car_status == 'own' and not self.request.participant.car:
            msg = (
                "You're a driver in the lottery, but haven't {edit_car}. "
                "If you can no longer drive, please update your {prefs}."
            )
            message = msg.format(
                edit_car=self.profile_link("submitted car information"),
                prefs=self.prefs_link(),
            )
            messages.warning(self.request, message, extra_tags='safe')

    def warn_if_no_ranked_trips(self):
        """ Warn the user if there are future signups, and none are ranked.

        Some participants don't understand the significance of signing up for
        multiple trips: Namely, they miss the fact that there's an easy way to
        set which ones are your favorite! This reminder gives them a quick link
        to let them rank their most preferred trips.
        """
        # Only consider signups for lottery trips in the future
        future_signups = models.SignUp.objects.filter(
            participant=self.request.participant,
            on_trip=False,
            trip__algorithm='lottery',
            trip__trip_date__gte=dateutils.local_date(),
        ).values_list('order', flat=True)
        some_trips_ranked = any(order for order in future_signups)

        if len(future_signups) > 1 and not some_trips_ranked:
            msg = "You haven't " + self.prefs_link("ranked upcoming trips.")
            messages.warning(self.request, msg, extra_tags='safe')

    def warn_if_dated_info(self):
        """ If the participant hasn't updated information in a while, remind
        them of their status as a driver. """
        if self.lotteryinfo:
            time_diff = timezone.now() - self.lotteryinfo.last_updated
            days_old = time_diff.days

            if days_old >= self.WARN_AFTER_DAYS_OLD:
                msg = (
                    "You haven't updated your {} in {} days. "
                    "You will be counted as a {}driver in the next lottery."
                )
                driver_prefix = "" if self.lotteryinfo.is_driver else "non-"
                msg = msg.format(self.prefs_link(), days_old, driver_prefix)
                messages.info(self.request, msg, extra_tags='safe')


def warn_if_needs_update(request):
    """ Create message if Participant info needs update. Otherwise, do nothing. """
    if not request.user.is_authenticated:
        return

    participant = request.participant
    if not participant:  # Authenticated, but no info yet
        msg = 'Personal information missing.'
    else:
        if participant.info_current:  # Record exists, is up to date
            return
        msg = 'Personal information is out of date.'

    edit_url = reverse('edit_profile')
    msg += ' <a href="{}">Update</a> to sign up for trips.'.format(edit_url)
    messages.warning(request, msg, extra_tags='safe')


def complain_if_missing_itineraries(request):
    """ Create messages if the leader needs to complete trip itineraries. """
    if not ws.utils.perms.is_leader(request.user):
        return

    now = dateutils.local_now()

    # Most trips require itineraries, but some (TRS, etc.) do not
    # All WS trips require itineraries, though
    future_trips_without_info = request.participant.trips_led.filter(
        trip_date__gte=now.date(), info__isnull=True, activity='winter_school'
    ).values_list('pk', 'trip_date', 'name')

    for trip_pk, trip_date, name in future_trips_without_info:
        if now > dateutils.itinerary_available_at(trip_date):
            trip_url = reverse('trip_itinerary', args=(trip_pk,))
            msg = (
                f'Please <a href="{trip_url}">submit an itinerary for '
                f'{escape(name)}</a> before departing!'
            )
            messages.warning(request, msg, extra_tags='safe')


def complain_if_missing_feedback(request):
    """ Create messages if the leader should supply feedback.

    We request that leaders leave feedback on all trips they've led.
    """
    if not ws.utils.perms.is_leader(request.user):
        return

    participant = request.participant

    today = dateutils.local_date()
    one_month_ago = today - timedelta(days=30)

    recent_trips_without_feedback = (
        participant.trips_led.filter(trip_date__lt=today, trip_date__gt=one_month_ago)
        .exclude(feedback__leader=participant)
        .values_list('pk', 'name')
    )

    for trip_pk, name in recent_trips_without_feedback:
        trip_url = reverse('review_trip', args=(trip_pk,))
        msg = f'Please supply feedback for <a href="{trip_url}">{escape(name)}</a>'
        messages.warning(request, msg, extra_tags='safe')


def warn_if_password_insecure(request):
    """ Warn if the participant's password is insecure.

    When a participant logs in with a known insecure password, they are
    redirected to the "change password" page. They *should* change their
    password immediately, but we don't mandate a password change before they can
    use the rest of the site.

    We *might* require an immediate password change in the future, but for now
    there are good reasons not to (for example, a participant is out on a
    weekend trip and needs to log in to access important trip information, but
    cannot easily generate a strong password with just their mobile device).

    This serves to warn people who ignore the message (and log that they ignored it,
    so we might use that data to inform a better password policy).
    """
    par = request.participant
    if par and par.insecure_password:
        change_password_url = reverse('account_change_password')
        msg = (
            'Your password is insecure! '
            f'Please <a href="{change_password_url}">change your password.</a>'
        )
        messages.error(request, msg, extra_tags='safe')

        logger.debug(
            "Warned participant %s ({%s}) about insecure password", par.pk, par.email
        )
