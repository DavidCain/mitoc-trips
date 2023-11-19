from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from ws.decorators import group_required


class StatsView(TemplateView):
    template_name = "stats/index.html"


class LeaderboardView(TemplateView):
    template_name = "stats/leaderboard.html"


class MembershipStatsView(TemplateView):
    template_name = "stats/membership.html"

    @method_decorator(group_required("leaders"))
    def dispatch(self, request, *args, **kwargs):
        # TODO: Restrict to BOD only
        return super().dispatch(request, *args, **kwargs)
