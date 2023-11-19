"""
Messages pertaining to the Winter School lottery.
"""

from django.contrib import messages
from django.urls import reverse
from django.utils import timezone

import ws.utils.dates as date_utils
from ws import enums, models

from . import MessageGenerator


class Messages(MessageGenerator):
    """Supply messages relating to lottery status of one participant."""

    WARN_AFTER_DAYS_OLD = 5  # After these days, remind of lottery status

    @property
    def lotteryinfo(self):
        participant = self.request.participant

        try:
            return participant and participant.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            return None

    def supply(self):
        if not self.request.participant or not date_utils.is_currently_iap():
            return
        self.warn_if_missing_lottery()
        self.warn_if_car_missing()
        self.warn_if_dated_info()

        if self.lotteryinfo:  # (warnings are redundant if no lottery info)
            self.warn_if_no_ranked_trips()

    @staticmethod
    def profile_link(text: str) -> str:
        # Remember to set extra_tags='safe' to avoid escaping HTML
        return f"""<a href="{reverse('edit_profile')}">{text}</a>"""

    @staticmethod
    def prefs_link(text: str = "lottery preferences") -> str:
        # Remember to set extra_tags='safe' to avoid escaping HTML
        return f"""<a href="{reverse('lottery_preferences')}">{text}</a>"""

    def warn_if_missing_lottery(self):
        """Warn if lottery information isn't found for the participant.

        Because car information and ranked trips are submitted in one form,
        checking participant.lotteryinfo is sufficient to check both.
        """
        if not self.lotteryinfo:
            prefs = self.prefs_link()
            self.add_unique_message(
                messages.WARNING, f"You haven't set your {prefs}.", extra_tags="safe"
            )

    def warn_if_car_missing(self):
        lottery = self.lotteryinfo
        if not lottery:
            return
        if lottery.car_status == "own" and not self.request.participant.car:
            edit_car = self.profile_link("submitted car information")
            prefs = self.prefs_link()
            msg = (
                f"You're a driver in the lottery, but haven't {edit_car}. "
                f"If you can no longer drive, please update your {prefs}."
            )
            self.add_unique_message(messages.WARNING, msg, extra_tags="safe")

    def warn_if_no_ranked_trips(self):
        """Warn the user if there are future signups, and none are ranked.

        Some participants don't understand the significance of signing up for
        multiple trips: Namely, they miss the fact that there's an easy way to
        set which ones are your favorite! This reminder gives them a quick link
        to let them rank their most preferred trips.
        """
        # Only consider signups for lottery trips in the future
        future_signups = models.SignUp.objects.filter(
            participant=self.request.participant,
            on_trip=False,
            trip__algorithm="lottery",
            trip__program=enums.Program.WINTER_SCHOOL.value,
            trip__trip_date__gte=date_utils.local_date(),
        ).values_list("order", flat=True)
        some_trips_ranked = any(order for order in future_signups)

        if len(future_signups) > 1 and not some_trips_ranked:
            msg = "You haven't " + self.prefs_link("ranked upcoming trips.")
            self.add_unique_message(messages.WARNING, msg, extra_tags="safe")

    def warn_if_dated_info(self):
        """Remind participants if they've not updated lottery preferences."""
        if not self.lotteryinfo:
            return

        time_diff = timezone.now() - self.lotteryinfo.last_updated
        days_old = time_diff.days

        if days_old < self.WARN_AFTER_DAYS_OLD:
            return

        prefs = self.prefs_link()
        driver_prefix = "" if self.lotteryinfo.is_driver else "non-"
        msg = (
            f"You haven't updated your {prefs} in {days_old} days. "
            f"You will be counted as a {driver_prefix}driver in the next lottery."
        )
        self.add_unique_message(messages.INFO, msg, extra_tags="safe")
