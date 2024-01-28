"""Mixins used across multiple views."""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import View

import ws.utils.perms as perm_utils
from ws import enums, models
from ws.utils.dates import is_currently_iap


class LotteryPairingMixin:
    """Gives information about lottery pairing.

    Requires a `participant` attribute.
    """

    participant: models.Participant

    @property
    def pair_requests(self):
        """Participants who have requested to be paired with the given participant."""
        requested = Q(lotteryinfo__paired_with=self.participant)
        return models.Participant.objects.filter(requested)

    @property
    def paired_par(self):
        """The participant this one requested to be paired with (if any)."""
        try:
            return self.participant.lotteryinfo.paired_with
        except models.LotteryInfo.DoesNotExist:
            return None

    @property
    def reciprocally_paired(self):
        """Return if the participant is reciprocally paired with another."""
        paired_par = self.paired_par
        if paired_par:
            try:
                return paired_par.lotteryinfo.paired_with == self.participant
            except models.LotteryInfo.DoesNotExist:
                return False
        return False


class LectureAttendanceMixin:
    """Manage the participant's lecture attendance."""

    request: HttpRequest

    def can_set_attendance(self, participant_to_modify: models.Participant) -> bool:
        """Return if the requesting user can set the participant's WS attendance."""
        # Only the WS chairs can set attendance for others.
        if participant_to_modify.user_id != self.request.user.id:
            return perm_utils.is_chair(
                self.request.user, enums.Activity.WINTER_SCHOOL, allow_superusers=True
            )

        # Setting your own attendance is only allowed when setting is on
        if not is_currently_iap():  # (Save a db query for the rest of the year)
            return False
        settings = models.WinterSchoolSettings.load()
        return settings.allow_setting_attendance


class TripTooOldError(Exception):
    pass


class NotATripLeaderError(Exception):
    pass


def _ensure_trip_modification_allowed(
    trip: models.Trip,
    request: HttpRequest,
    forbid_old_trips: bool = False,
) -> None:
    activity_enum = trip.required_activity_enum()
    is_chair = (
        perm_utils.chair_or_admin(request.user, activity_enum)
        if activity_enum
        # There is no required activity, so no chairs. Allow superusers, though
        else request.user.is_superuser
    )

    if is_chair:
        return

    if forbid_old_trips:
        cutoff_date = (timezone.localtime() - timedelta(days=30)).date()
        if trip.trip_date < cutoff_date:
            raise TripTooOldError

    participant: models.Participant = request.participant  # type: ignore[attr-defined]
    if not perm_utils.leader_on_trip(participant, trip, True):
        raise NotATripLeaderError


class TripLeadersOnlyView(View):
    forbid_modifying_old_trips: bool

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        """Only allow creator, leaders of the trip, and chairs."""
        forbid_old_trips = getattr(self, "forbid_modifying_old_trips", False)

        trip = self.get_object()
        try:
            _ensure_trip_modification_allowed(trip, request, forbid_old_trips)
        except TripTooOldError:
            return render(request, "cannot_edit_old_trip.html", {"trip": trip})
        except NotATripLeaderError:
            return render(request, "not_your_trip.html", {"trip": trip})

        return super().dispatch(request, *args, **kwargs)


class JsonTripLeadersOnlyView(View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        """Only allow creator, leaders of the trip, and chairs."""
        try:
            _ensure_trip_modification_allowed(self.get_object(), request)
        except NotATripLeaderError:
            return JsonResponse({"message": "Must be a leader"}, status=403)
        return super().dispatch(request, *args, **kwargs)
