from collections import defaultdict
from datetime import date, timedelta
from typing import Any, TypedDict, cast
from urllib.parse import urlencode

from django.db.models import Q, QuerySet
from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBase,
    HttpResponseRedirect,
)
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.generic import FormView, TemplateView

from ws import enums, forms, icons, models
from ws.decorators import group_required
from ws.utils.dates import local_date
from ws.utils.member_stats import CacheStrategy


class StatsView(TemplateView):
    template_name = "stats/index.html"


class SearchFields(TypedDict):
    start_date: date
    end_date: date | None
    # String values can all be empty. If non-empty, they passed validation.
    q: str
    program: str
    winter_terrain_level: str
    trip_type: str


def summarize_filters(cleaned_data: SearchFields) -> str:
    """Provide a human summary of the query (for use in the leaderboard title)."""
    descriptors: list[str] = []
    comma_separated_extras: list[str] = []

    trip_type = (
        enums.TripType(cleaned_data["trip_type"]) if cleaned_data["trip_type"] else None
    )
    program = (
        enums.Program(cleaned_data["program"]) if cleaned_data["program"] else None
    )

    if trip_type:
        descriptors.append(trip_type.label)
    if cleaned_data["winter_terrain_level"]:
        descriptors.append(cleaned_data["winter_terrain_level"])

    if program:
        # Avoid mouthfuls like "Climbing gym climbing" or "Boating surfing"
        if trip_type:
            comma_separated_extras.append(program.label)
        else:
            descriptors.insert(0, program.label)

    if not descriptors:
        descriptors.append("All")
    if cleaned_data["q"]:
        descriptors.append(repr(cleaned_data["q"]))

    start_date = cleaned_data["start_date"]
    end_date = cleaned_data["end_date"]

    date_range = (
        f"between {start_date} and {end_date}" if end_date else f"since {start_date}"
    )

    summary = f"{' '.join(descriptors)} trips led {date_range}"
    return ", ".join([summary, *comma_separated_extras])


class LeaderboardView(TemplateView, FormView):
    form_class = forms.TripSearchForm
    template_name = "stats/leaderboard.html"

    @method_decorator(group_required("leaders"))
    def dispatch(
        self, request: HttpRequest, *args: Any, **kwargs: Any
    ) -> HttpResponseBase:
        return super().dispatch(request, *args, **kwargs)

    def _default_start_date(self) -> date:
        return local_date() - timedelta(days=365)

    def form_valid(self, form: forms.TripSearchForm) -> HttpResponseRedirect:
        """Populate successful form contents into the URL."""
        params = {
            label: form.cleaned_data[label]
            for label in form.declared_fields
            if form.cleaned_data[label]
        }
        url = reverse("leaderboard")
        if params:
            url += f"?{urlencode(params)}"
        return redirect(url)

    def _get_trips(self, cleaned_data: SearchFields) -> QuerySet[models.Trip]:
        specified_filters: dict[str, Any] = {
            "trip_date__gte": cleaned_data["start_date"]
        }
        specified_filters.update(
            {
                field: value
                for field, value in cleaned_data.items()
                if value and field in {"winter_terrain_level", "trip_type", "program"}
            }
        )
        if cleaned_data["end_date"]:
            specified_filters["trip_date__lte"] = cleaned_data["end_date"]

        return models.Trip.objects.filter(Q(**specified_filters))

    def get_rows(self, cleaned_data: SearchFields) -> list[dict[str, str | int]]:
        """Produce the table rows describing the matched leaders."""
        total_trips_led: dict[models.Participant, int] = {}

        by_program: dict[models.Participant, defaultdict[enums.Program, int]] = {}

        # We'll be counting trips in a variety of ways per-leader.
        # Rather than a bunch of SQL aggregations, just do it in plain Python.
        for trip in self._get_trips(cleaned_data).prefetch_related("leaders"):
            for leader in trip.leaders.all():
                total_trips_led[leader] = total_trips_led.get(leader, 0) + 1
                by_program.setdefault(leader, defaultdict(int))[trip.program_enum] += 1

        all_programs = sorted(
            {program for programs in by_program.values() for program in programs},
            key=lambda program: program.label,
        )

        return [
            {
                "Name": format_html(
                    '<a href="/participants/{}/">{}</a>', par.pk, par.name
                ),
                "Email": par.email,
                "Trips led": total_trips_led[par],
                **{
                    format_html(
                        '<span uib-tooltip="{}"><i class="{}"></i></span>',
                        program.label,
                        f"fa fw fa-{icons.ICON_BY_PROGRAM[program] or 'times'}",
                    ): by_program[par].get(program, 0)
                    for program in all_programs
                },
            }
            for par in sorted(
                total_trips_led,
                # The leaderboard is primarily used for competition.
                # Sort by number of trips led, not just alphabetical.
                key=lambda par: (-total_trips_led[par], par.name, par.pk),
            )
        ]

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # This view implements some form logic directly allowing query args.
        # So as to handle the case of loading the page with invalid args, validate!
        form = self.form_class(self.request.GET)
        if not form.is_valid():
            return self.form_invalid(form)
        return super().get(request, *args, **kwargs)

    def get_initial(self) -> dict[str, str]:
        """Use the querystring to populate the form."""
        initial = {
            label: self.request.GET.get(label, "")
            for label in self.form_class.declared_fields
        }
        if not initial["start_date"]:
            initial["start_date"] = self._default_start_date().isoformat()
        return initial

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data()
        form = self.form_class(self.request.GET.dict())

        # We can only render a title & rows with a valid query.
        if not form.is_valid():
            return context
        cleaned_data = cast(
            SearchFields,
            {
                **form.cleaned_data,
                "start_date": (
                    # It's valid for there to be no start date in the querystring.
                    # Still fall back though to the default!
                    form.cleaned_data["start_date"] or self._default_start_date()
                ),
            },
        )
        rows = self.get_rows(cleaned_data)

        return {
            **context,
            "rows": rows,
            "leaderboard_title": summarize_filters(cleaned_data),
        }


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
