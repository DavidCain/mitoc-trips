"""
Messages pertaining to the Winter School lottery.
"""

from django.contrib import messages
from django.urls import reverse
from django.utils import timezone

import ws.utils.dates as dateutils
from ws import models

from . import MessageGenerator


class Messages(MessageGenerator):
    """ Supply messages relating to lottery status of one participant. """

    WARN_AFTER_DAYS_OLD = 5  # After these days, remind of lottery status

    @property
    def lotteryinfo(self):
        participant = self.request.participant
        if not participant:
            return None

        try:
            return participant.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            return None

    def supply(self):
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
