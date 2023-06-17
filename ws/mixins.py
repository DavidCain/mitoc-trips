"""
Mixins used across multiple views.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
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


def _allowed_to_modify_trip(trip: models.Trip, request: HttpRequest) -> bool:
    activity_enum = trip.required_activity_enum()
    if activity_enum:
        is_chair = perm_utils.chair_or_admin(request.user, activity_enum)
    else:  # (There is no required activity, so no chairs. Allow superusers, though)
        is_chair = request.user.is_superuser

    participant: models.Participant = request.participant  # type: ignore[attr-defined]
    trip_leader = perm_utils.leader_on_trip(participant, trip, True)
    return is_chair or trip_leader


class TripLeadersOnlyView(View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        """Only allow creator, leaders of the trip, and chairs."""

        trip = self.get_object()
        if not _allowed_to_modify_trip(trip, request):
            return render(request, 'not_your_trip.html', {'trip': trip})
        return super().dispatch(request, *args, **kwargs)


class JsonTripLeadersOnlyView(View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        """Only allow creator, leaders of the trip, and chairs."""
        if not _allowed_to_modify_trip(self.get_object(), request):
            return JsonResponse({"message": "Must be a leader"}, status=403)
        return super().dispatch(request, *args, **kwargs)
