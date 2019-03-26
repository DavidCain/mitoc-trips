"""
Mixins used across multiple views.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views.generic import View

import ws.utils.perms as perm_utils
from ws import models
from ws.utils.dates import is_winter_school


class LotteryPairingMixin:
    """ Gives information about lottery pairing.

    Requires a `participant` attribute.
    """

    @property
    def pair_requests(self):
        requested = Q(lotteryinfo__paired_with=self.participant)
        return models.Participant.objects.filter(requested)

    @property
    def paired_par(self):
        try:
            return self.participant.lotteryinfo.paired_with
        except models.LotteryInfo.DoesNotExist:
            return None

    @property
    def reciprocally_paired(self):
        """ Return if the participant is reciprocally paired with another. """
        paired_par = self.paired_par
        if paired_par:
            try:
                return paired_par.lotteryinfo.paired_with == self.participant
            except models.LotteryInfo.DoesNotExist:
                return False
        return False


class LectureAttendanceMixin:
    """ Manage the participant's lecture attendance. """

    def can_set_attendance(self, participant):
        # WS chairs can set any time for any user
        if perm_utils.is_chair(self.request.user, 'winter_school', True):
            return True

        # Non-chairs are only allowed during WS when setting enabled
        if not is_winter_school():
            return False
        settings = models.WinterSchoolSettings.load()
        if not settings.allow_setting_attendance:
            return False

        # Non-chairs may only set attendance for themselves
        return participant == self.request.participant


class TripLeadersOnlyView(View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        """ Only allow creator, leaders of the trip, and chairs. """
        trip = self.get_object()
        chair = perm_utils.chair_or_admin(request.user, trip.activity)
        trip_leader = perm_utils.leader_on_trip(request.participant, trip, True)
        if not (chair or trip_leader):
            return render(request, 'not_your_trip.html', {'trip': trip})
        return super().dispatch(request, *args, **kwargs)
