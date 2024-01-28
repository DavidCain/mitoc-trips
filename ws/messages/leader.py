"""Messages for leaders!"""
from datetime import timedelta

from django.contrib import messages
from django.urls import reverse
from django.utils.html import escape

import ws.utils.dates as date_utils
import ws.utils.perms as perm_utils
from ws import enums

from . import MessageGenerator


class Messages(MessageGenerator):
    def supply(self):
        if not perm_utils.is_leader(self.request.user):
            return
        self._complain_if_missing_itineraries()
        self._complain_if_missing_feedback()

    def _complain_if_missing_itineraries(self):
        """Create messages if the leader needs to complete trip itineraries."""
        now = date_utils.local_now()

        # Most trips require itineraries, but some (TRS, etc.) do not
        # All WS trips require itineraries, though
        future_trips_without_info = (
            self.request.participant.trips_led.filter(
                trip_date__gte=now.date(),
                info__isnull=True,
                program=enums.Program.WINTER_SCHOOL.value,
            )
            .order_by("trip_date")  # Warn about closest trips first!
            .values_list("pk", "trip_date", "name")
        )

        for trip_pk, trip_date, name in future_trips_without_info:
            if now > date_utils.itinerary_available_at(trip_date):
                trip_url = reverse("trip_itinerary", args=(trip_pk,))
                msg = (
                    f'Please <a href="{trip_url}">submit an itinerary for '
                    f"{escape(name)}</a> before departing!"
                )
                self.add_unique_message(messages.WARNING, msg, extra_tags="safe")

    def _complain_if_missing_feedback(self):
        """Create messages if the leader should supply feedback.

        We request that leaders leave feedback on all trips they've led.
        """
        participant = self.request.participant

        today = date_utils.local_date()
        one_month_ago = today - timedelta(days=30)

        recent_trips_without_feedback = (
            participant.trips_led.filter(
                trip_date__lt=today, trip_date__gt=one_month_ago
            )
            .exclude(feedback__leader=participant)
            .exclude(signup__isnull=True)  # Don't bother with empty trips
            .values_list("pk", "name")
        )

        for trip_pk, name in recent_trips_without_feedback:
            trip_url = reverse("review_trip", args=(trip_pk,))
            msg = f'Please supply feedback for <a href="{trip_url}">{escape(name)}</a>'
            self.add_unique_message(messages.WARNING, msg, extra_tags="safe")
