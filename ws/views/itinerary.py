"""Views relating to a trip's itinerary management, & medical information.

Each official trip should have an itinerary completed by trip leaders.
That itinerary specifies who (if anybody) will be driving for the trip,
what the intended route will be, when to worry, and more.
"""

from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.forms.utils import ErrorList
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import (
    DetailView,
    FormView,
    ListView,
    RedirectView,
    UpdateView,
)

import ws.utils.perms as perm_utils
from ws import enums, forms, models, wimp
from ws.decorators import group_required
from ws.mixins import TripLeadersOnlyView
from ws.utils.dates import itinerary_available_at, local_date, local_now
from ws.utils.itinerary import approve_trip


class TripItineraryView(UpdateView, TripLeadersOnlyView):
    """A hybrid view for creating/editing trip info for a given trip."""

    model = models.Trip
    context_object_name = "trip"
    template_name = "trips/itinerary.html"
    form_class = forms.TripInfoForm

    # This class has its own logic for preventing edits
    forbid_modifying_old_trips = False

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trip = context["trip"]
        context["itinerary_available_at"] = itinerary_available_at(trip.trip_date)
        context["info_form_editable"] = trip.info_editable
        if local_now() < context["itinerary_available_at"]:
            context["waiting_to_open"] = True
            context["form"].fields.pop("accurate")
            for field in context["form"].fields.values():
                field.disabled = True
        return context

    def get_initial(self) -> dict[str, Any]:
        self.trip = self.get_object()
        return {"trip": self.trip}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.trip.info
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        signups = self.trip.signup_set.filter(on_trip=True)
        on_trip = Q(pk__in=self.trip.leaders.all()) | Q(signup__in=signups)
        participants = models.Participant.objects.filter(on_trip).distinct()
        has_car_info = participants.filter(car__isnull=False)
        form.fields["drivers"].queryset = has_car_info
        return form

    def form_valid(self, form):
        if not self.trip.info_editable:
            verb = "modified" if self.trip.info else "created"
            form.errors["__all__"] = ErrorList([f"Itinerary cannot be {verb}"])
            return self.form_invalid(form)
        self.trip.info = form.save()
        self.trip.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("view_trip", args=(self.trip.pk,))


class AllTripsMedicalView(ListView):
    model = models.Trip
    template_name = "trips/all/medical.html"
    context_object_name = "trips"

    def get_queryset(self):
        trips = super().get_queryset().order_by("trip_date")
        today = local_date()
        return trips.filter(trip_date__gte=today)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data["wimps"] = wimp.active_wimps()
        return context_data

    @method_decorator(group_required({"WSC", "WIMP"}))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TripMedicalView(DetailView):
    model = models.Trip
    template_name = "trips/medical.html"

    @staticmethod
    def _can_view(trip, request):
        """Leaders, chairs, and a trip WIMP can view this page."""
        return (
            perm_utils.in_any_group(request.user, {"WIMP"})
            or (trip.wimp and request.participant == trip.wimp)
            or perm_utils.leader_on_trip(request.participant, trip, True)
            or perm_utils.chair_or_admin(request.user, trip.required_activity_enum())
        )

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        """Only allow creator, leaders of the trip, WIMP, and chairs."""
        # The normal `dispatch()` will populate self.object
        normal_response = super().dispatch(request, *args, **kwargs)

        trip = self.object
        if not self._can_view(trip, request):
            return render(request, "not_your_trip.html", {"trip": trip})
        return normal_response

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        """Get a trip info form for display as readonly."""
        context_data = super().get_context_data(**kwargs)
        trip = self.object
        participant = self.request.participant  # type: ignore[attr-defined]
        return {
            "is_trip_leader": perm_utils.leader_on_trip(participant, trip),
            "has_wimp": (
                trip.program_enum == enums.Program.WINTER_SCHOOL
                or (trip.wimp_id is not None)
            ),
            **context_data,
        }


class ChairTripView(RedirectView):
    """Redirect to the most-current version of the trip.

    This view serves two useful purposes:

    1. We can easily link to "whatever the most current version of the trip is"
       (ensuring that the most recent version is always shown if/when the link
       is actually clicked)
       - NOTE: The present implementation will *always* redirect to newer trip
         versions, though, so you can always link to an arbirary version and
         still assume that a redirect will occur. It's probably better UX
         for humans though if we don't hard link to a specific version
         (only to redirect away from that version)
    2. We can still serve old URLs that did not have the version
    """

    # There's zero harm in exposing a trip's version to anybody with creds.
    # (we're only redirecting, the next view will handle creds)
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_redirect_url(self, *args: Any, **kwargs: Any) -> str:
        trip_id = kwargs["pk"]
        try:
            trip = models.Trip.objects.get(pk=trip_id)
        except models.Trip.DoesNotExist as e:
            raise Http404 from e

        return reverse(
            "view_versioned_trip_for_approval",
            kwargs={
                # Might as well just correct the activity if it's wrong...
                "activity": trip.activity,
                "pk": trip.pk,
                "edit_revision": trip.edit_revision,
            },
        )


class VersionedChairTripView(DetailView, FormView):
    """Give a view of the trip intended to let chairs approve or not.

    Will show just the important details, like leaders, description, & itinerary.
    """

    model = models.Trip
    form_class = forms.ChairApprovalForm
    template_name = "chair/trips/view.html"

    def get(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        """Redirect to the current trip version if an old/incorrect one was requested.

        At least for now (and likely into the future), we can't load old versions.
        If an old or incorrect version was requested, redirect to the newest version.

        This redirect serves two key purposes:
        1. It ensures the UI is not incorrectly implying "this was the older trip version's info"
        2. If/when an activity chair clicks "approve," we record the correct version they saw.
        """
        trip = self.get_object()
        if trip.edit_revision != kwargs["edit_revision"]:
            if not (0 <= kwargs["edit_revision"] <= trip.edit_revision):
                messages.warning(
                    self.request,
                    "Requested a trip version that's never existed. Redirecting to the latest.",
                )
            return redirect(
                reverse(
                    # WARNING: it's technically possible for this to be an infinite redirect loop.
                    # In practice, that shouldn't happen.
                    "view_versioned_trip_for_approval",
                    kwargs={
                        "activity": kwargs["activity"],
                        "pk": trip.pk,
                        "edit_revision": trip.edit_revision,
                    },
                ),
            )
        return super().get(request, **kwargs)

    def get_initial(self) -> dict[str, Any]:
        trip = self.get_object()
        return {
            "trip": trip,
            "trip_edit_revision": trip.edit_revision,
            "approver": self.request.participant,  # type: ignore[attr-defined]
        }

    @property
    def activity_enum(self) -> enums.Activity:
        """Note that this may raise a ValueError if given an unknown activity!"""
        return enums.Activity(self.kwargs["activity"])

    def get_queryset(self) -> QuerySet[models.Trip]:
        """All trips of this activity type.

        For identifying only trips that need attention, callers
        should probably also filter on `trip_date` and `chair_approved`.

        By declining to filter here, this prevents a 404 on past trips.
        (In other words, a trip in the past that may or may not have been
        approved can still be viewed as it would have been for activity chairs)
        """
        # Order by the same ordering that's given on the "Trips needing approval" table
        return models.Trip.objects.filter(activity=self.activity_enum.value).order_by(
            *models.Trip.ordering_for_approval
        )

    def get_other_trips(self) -> tuple[models.Trip | None, models.Trip | None]:
        """Get the trips that come before and after this trip & need approval."""
        this_trip = self.get_object()

        ordered_trips = iter(
            self.get_queryset().filter(
                chair_approved=False, trip_date__gte=local_date()
            )
        )

        prev_trip = None
        for trip in ordered_trips:
            if trip.pk == this_trip.pk:
                try:
                    next_trip = next(ordered_trips)
                except StopIteration:
                    next_trip = None
                break
            prev_trip = trip
        else:
            return None, None  # (Could be the last unapproved trip)
        return prev_trip, next_trip

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        trip = self.get_object()
        prev_trip, next_trip = self.get_other_trips()
        approvals = (
            models.ChairApproval.objects.filter(trip_id=trip.pk)
            .select_related("approver")
            .order_by("-pk")
        )
        return {
            **super().get_context_data(**kwargs),
            "activity_enum": self.activity_enum,
            "prev_trip": prev_trip,
            "next_trip": next_trip,
            "approvals": approvals,
            "last_approval": approvals[0] if approvals else None,
        }

    def form_valid(self, form: forms.ChairApprovalForm) -> HttpResponse:
        trip = self.get_object()
        _, next_trip = self.get_other_trips()  # Do this before saving trip
        approve_trip(
            trip,
            approving_chair=self.request.participant,  # type: ignore[attr-defined]
            trip_edit_revision=form.cleaned_data["trip_edit_revision"],
            notes=form.cleaned_data["notes"],
        )
        if next_trip:
            return redirect(
                reverse(
                    "view_versioned_trip_for_approval",
                    kwargs={
                        "activity": self.activity_enum.value,
                        "pk": next_trip.pk,
                        # This is *likely* the most current version.
                        # (If not, we'll be redirected again to the proper one)
                        "edit_revision": next_trip.edit_revision,
                    },
                )
            )

        return redirect(reverse("manage_trips", args=(self.activity_enum.value,)))

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        try:
            enums.Activity(self.kwargs["activity"])
        except ValueError:
            raise Http404  # noqa: B904

        trip = self.get_object()
        if not perm_utils.is_chair(request.user, trip.required_activity_enum()):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
