from django.http import HttpRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from ws import models
from ws.decorators import group_required
from ws.utils.member_stats import CacheStrategy


class StatsView(TemplateView):
    template_name = "stats/index.html"


class LeaderboardView(TemplateView):
    template_name = "stats/leaderboard.html"


class MembershipStatsView(TemplateView):
    template_name = "stats/membership.html"

    def get_context_data(self, **kwargs):
        cache_strategy = self._validated_cache_strategy(self.request)

        context = super().get_context_data()
        context["cache_strategy"] = cache_strategy.value

        if cache_strategy is CacheStrategy.FETCH_IF_STALE_ASYNC:
            # We can report the stats last retrieval *before* the XHR.
            # (This works because the API endpoint will *always* report the cache!)
            cached = models.MembershipStats.load()
            context["retrieved_at"] = cached.retrieved_at

        return context

    @staticmethod
    def _validated_cache_strategy(request: HttpRequest) -> CacheStrategy:
        cache_str = request.GET.get(
            "cache_strategy",
            CacheStrategy.FETCH_IF_STALE_ASYNC.value,  # "default"
        )
        return CacheStrategy(cache_str)

    @method_decorator(group_required("leaders"))  # TODO: Restrict to BOD only?
    def dispatch(self, request, *args, **kwargs):
        try:
            self._validated_cache_strategy(request)
        except ValueError:
            # Just use the default, but redirect to make it clear it's not handled
            return redirect(reverse("membership_stats"))

        return super().dispatch(request, *args, **kwargs)
