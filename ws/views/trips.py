"""Trip views.

A "trip" is any official trip registered in the system - created by leaders, to be
attended by any interested participants.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, QuerySet
from django.forms.fields import TypedChoiceField
from django.forms.utils import ErrorList
from django.http import (
    Http404,
    HttpRequest,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    UpdateView,
)

import ws.utils.dates as date_utils
import ws.utils.perms as perm_utils
import ws.utils.signups as signup_utils
from ws import enums, forms, models
from ws.decorators import group_required
from ws.lottery.run import SingleTripLotteryRunner
from ws.mixins import TripLeadersOnlyView
from ws.templatetags.trip_tags import annotated_for_trip_list
from ws.utils.dates import is_currently_iap, local_date
from ws.utils.geardb import outstanding_items

if TYPE_CHECKING:
    from ws.middleware import RequestWithParticipant


# Hardcode the result of `models.Trip.objects.earliest('trip_date')
# There will never be any *older* trips, so we can save db queries.
FIRST_TRIP_DATE = date(2015, 1, 10)

TRIPS_LOOKBACK = models.Trip.TRIPS_LOOKBACK


def _earliest_allowed_anon_lookback_date() -> date:
    return local_date() - TRIPS_LOOKBACK


class TripView(DetailView):
    """Display the trip to both unregistered users and known participants.

    For unregistered users, the page will have minimal information (a description,
    and leader names). For other participants, the controls displayed to them
    will vary depending on their permissions.
    """

    model = models.Trip
    context_object_name = "trip"
    template_name = "trips/view.html"

    object: models.Trip

    def get_queryset(self):
        trips = super().get_queryset().select_related("info")
        return trips.prefetch_related("leaders", "leaders__leaderrating_set")

    def get_participant_signup(self, trip=None):
        """Return viewer's signup for this trip (if one exists, else None)"""
        if not self.request.participant:
            return None
        trip = trip or self.get_object()
        return self.request.participant.signup_set.filter(trip=trip).first()

    @staticmethod
    def rentals_by_participant(trip):
        """Yield all items rented by leaders & participants on this trip.

        WARNING: This makes an API call and can block page load.
        We should probably make this method into its own view, or instead make
        a frontend component do the fetching asynchronously.

        Alternately, we could introduce a caching layer to make this viable hitting
        the database directly (like we do with the Membership model).
        """
        on_trip = trip.signup_set.filter(on_trip=True).select_related("participant")
        trip_participants = [s.participant for s in on_trip]
        leaders = list(trip.leaders.all())

        par_by_user_id = {par.user_id: par for par in trip_participants + leaders}
        if not par_by_user_id:  # No leaders or participants on the trip
            return

        emails = models.EmailAddress.objects.filter(
            verified=True, user_id__in=par_by_user_id
        )
        participant_by_email = {
            addr.email: par_by_user_id[addr.user_id] for addr in emails
        }
        gear_per_participant = defaultdict(list)
        for item in outstanding_items(list(participant_by_email)):
            if item.checkedout > trip.trip_date:
                continue  # This item definitely wasn't rented for the trip
            participant = participant_by_email[item.email]
            gear_per_participant[participant].append(item)

        # Yield in order of leaders & default signup ordering
        for par in leaders + trip_participants:
            if par in gear_per_participant:
                yield par, gear_per_participant[par]

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        trip = self.object

        context["leader_on_trip"] = perm_utils.leader_on_trip(
            self.request.participant, trip, True
        )
        context["can_admin"] = context["leader_on_trip"] or perm_utils.chair_or_admin(
            self.request.user, trip.required_activity_enum()
        )

        context["can_see_rentals"] = context["can_admin"] or perm_utils.is_leader(
            self.request.user
        )

        if context["can_admin"] or perm_utils.is_leader(self.request.user):
            context["show_rentals_inline"] = "show_rentals_inline" in self.request.GET
            if context["show_rentals_inline"]:
                context["rentals_by_par"] = list(self.rentals_by_participant(trip))

        return context

    def post(self, request, *args, **kwargs):
        """Add signup to trip or waitlist, if applicable.

        Used if the participant has signed up, but wasn't placed.
        """
        signup = self.get_participant_signup()
        signup_utils.trip_or_wait(signup, self.request, trip_must_be_open=True)
        return self.get(request)


class ReviewTripView(DetailView):
    model = models.Trip
    template_name = "trips/review.html"
    success_msg = "Thanks for your feedback!"

    object: models.Trip
    request: "RequestWithParticipant"

    @property
    def posted_feedback(self):
        """Convert named fields of POST data to participant -> feedback mapping.

        If the form data was garbled (intentionally or otherwise), this method
        will raise ValueError or TypeError (on either 'split' or `int`)
        """
        for key, comments in self.request.POST.items():
            if not (key.startswith(("par_", "flake_"))):
                continue

            feedback_type, par_pk = key.split("_")
            showed_up = feedback_type == "par"

            yield int(par_pk), comments.strip(), showed_up

    def post(self, request, *args, **kwargs):
        """Create or update all feedback passed along in form data."""
        trip = self.object = self.get_object()
        if trip.feedback_window_passed:
            messages.warning(
                self.request,
                "Trip feedback window has passed. Feedback may not be updated.",
            )
            return redirect(reverse("review_trip", args=(trip.pk,)))

        leader = self.request.participant

        try:
            posted_feedback = list(self.posted_feedback)
        except (TypeError, ValueError):
            # This should never happen, but look at doing this more nicely?
            return HttpResponseBadRequest("Invalid form contents")

        # Create or update feedback for all feedback passed in the form
        existing_feedback = {
            feedback.participant.pk: feedback
            for feedback in self.get_existing_feedback()
        }
        for pk, comments, showed_up in posted_feedback:
            blank_feedback = showed_up and not comments
            existing = existing_feedback.get(pk)

            if existing and blank_feedback:
                existing.delete()
                continue

            if existing is not None:
                feedback = existing
            elif blank_feedback:
                continue  # Don't create new feedback saying nothing useful
            else:
                kwargs = {
                    "leader": leader,
                    "trip": trip,
                    "participant": models.Participant.objects.get(pk=pk),
                }
                feedback = models.Feedback.objects.create(**kwargs)

            feedback.comments = comments
            feedback.showed_up = showed_up
            feedback.save()

        messages.success(self.request, self.success_msg)
        return redirect(reverse("home"))

    @property
    def trip_participants(self):
        accepted_signups = self.object.signup_set.filter(on_trip=True)
        accepted_signups = accepted_signups.select_related("participant")
        return [signup.participant for signup in accepted_signups]

    def get_existing_feedback(self) -> QuerySet[models.Feedback]:
        leader = self.request.participant
        return models.Feedback.objects.filter(trip=self.object, leader=leader)

    @property
    def feedback_list(self):
        feedback = self.get_existing_feedback()
        par_comments = dict(feedback.values_list("participant__pk", "comments"))
        return [(par, par_comments.get(par.pk, "")) for par in self.trip_participants]

    def get_context_data(self, **kwargs):
        today = local_date()
        trip = self.object = self.get_object()
        return {
            "trip": trip,
            "feedback_window_passed": trip.feedback_window_passed,
            "trip_completed": today >= trip.trip_date,
            "feedback_required": trip.program_enum == enums.Program.WINTER_SCHOOL,
            "feedback_list": self.feedback_list,
        }

    @method_decorator(group_required("leaders"))
    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        if not perm_utils.leader_on_trip(request.participant, trip, False):
            return render(request, "not_your_trip.html", {"trip": trip})
        return super().dispatch(request, *args, **kwargs)


class CreateTripView(CreateView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = "trips/create.html"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["initial"] = kwargs.get("initial", {})
        if not self.request.user.is_superuser:
            allowed_programs = list(self.request.participant.allowed_programs)
            kwargs["allowed_programs"] = allowed_programs

            if is_currently_iap() and enums.Program.WINTER_SCHOOL in allowed_programs:
                kwargs["initial"]["program"] = enums.Program.WINTER_SCHOOL.value
            else:
                # The first program may not be open to the leader.
                # We restrict choices, so ensure leader can lead this program.
                allowed_program = next(iter(allowed_programs))
                kwargs["initial"]["program"] = allowed_program.value
        return kwargs

    def get_success_url(self):
        return reverse("view_trip", args=(self.object.pk,))

    def get_initial(self):
        """Default with trip creator among leaders."""
        initial = super().get_initial().copy()
        # It's possible for WSC to create trips while not being a leader
        if perm_utils.is_leader(self.request.user):
            initial["leaders"] = [self.request.participant]
        return initial

    def form_valid(self, form):
        """After is_valid(), assign creator from User, set text description, add empty waitlist."""
        creator = self.request.participant
        trip = form.save(commit=False)
        if not trip.summary:
            trip.summary = trip.description_to_text(
                maxchars=models.Trip.summary.field.max_length
            )
        trip.creator = creator
        trip.last_updated_by = creator
        trip.activity = trip.get_legacy_activity()
        return super().form_valid(form)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["is_currently_iap"] = is_currently_iap()

        # There is separate logic for determining if we allow choosing the WS program.
        # Rather than duplicate that logic here, just see if it's a selectable choice.
        form: forms.TripForm = context["form"]
        program_field = cast(TypedChoiceField, form.fields["program"])
        context["can_select_ws_program"] = any(
            enums.Program(value) == enums.Program.WINTER_SCHOOL
            for category, choices in program_field.choices
            for value, label in choices
        )
        return context

    @method_decorator(group_required("leaders"))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


# Ignore a `mypy` issue (for now?) where `DeleteView` and `DeletionMixin`
# do not seem compatible:
# Definition of "object" in base class "DeletionMixin"
# is incompatible with definition in base class "BaseDetailView"
class DeleteTripView(DeleteView, TripLeadersOnlyView):  # type: ignore[misc]
    forbid_modifying_old_trips = True
    model = models.Trip
    success_url = reverse_lazy("trips")

    def get(self, request, *args, **kwargs):
        """Request is valid, but method is not (use POST)."""
        messages.warning(self.request, "Use delete button to remove trips.")
        return redirect(reverse("view_trip", kwargs=self.kwargs))


class EditTripView(UpdateView, TripLeadersOnlyView):
    forbid_modifying_old_trips = True

    model = models.Trip
    form_class = forms.TripForm
    template_name = "trips/edit.html"

    object: models.Trip

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not self.request.user.is_superuser:
            kwargs["allowed_programs"] = list(self.request.participant.allowed_programs)
        return kwargs

    @property
    def update_rescinds_approval(self) -> bool:
        trip = self.object
        activity_enum = trip.required_activity_enum()
        if activity_enum is None:
            return False  # No required activity, thus no chair to rescind"

        return (
            trip.chair_approved
            and trip.trip_date >= local_date()
            and not perm_utils.is_chair(self.request.user, activity_enum)
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["update_rescinds_approval"] = self.update_rescinds_approval
        return context

    def get_success_url(self):
        return reverse("view_trip", args=(self.object.pk,))

    def _leaders_changed(self, form: forms.TripForm) -> bool:
        old_pks = {leader.pk for leader in self.object.leaders.all()}
        new_pks = {leader.pk for leader in form.cleaned_data["leaders"]}
        return bool(old_pks.symmetric_difference(new_pks))

    def _ignore_leaders_if_unchanged(self, form):
        """Don't update the leaders m2m field if unchanged.

        This is a hack to avoid updating the m2m set (normally cleared, then
        reset) Without this, post_add (signal used to send emails) will send
        out a message to all leaders on _every_ trip update.

        A compromise: Only send emails when the leader list is changed.
        See ticket 6707 for an eventual fix to this behavior
        """
        if not self._leaders_changed(form):
            form.cleaned_data.pop("leaders")

    def _stale_revision_message(
        self,
        form: forms.TripForm,
        current_trip: models.Trip,
        new_trip: models.Trip,
    ) -> str | None:
        """Produce a message describing a stale edit, if one exists.."""
        if current_trip.edit_revision == new_trip.edit_revision:
            return None

        fields_with_difference = [
            field
            for name, field in form.fields.items()
            if name != "edit_revision"
            and getattr(current_trip, name) != getattr(new_trip, name)
        ]
        # (Account for the fact that we might have stripped `leaders`)
        if "leaders" in form.cleaned_data and self._leaders_changed(form):
            fields_with_difference.insert(0, form.fields["leaders"])

        if current_trip.last_updated_by is None:
            # This shouldn't ever happen, but the data model makes it possible
            editor_name = "an unknown user"
        elif current_trip.last_updated_by == self.request.participant:  # type: ignore[attr-defined]
            editor_name = "you"
        else:
            editor_name = current_trip.last_updated_by.name

        assert current_trip.edit_revision > new_trip.edit_revision
        edit_count = current_trip.edit_revision - new_trip.edit_revision
        plural = "" if edit_count == 1 else "s"

        differing_fields: list[str] = [
            # Handle the label being nullable or a `_StrPromise`
            str(field.label or "Unknown")
            for field in fields_with_difference
        ]
        return "\n".join(
            [
                f"This trip has already been edited {edit_count} time{plural}, most recently by {editor_name}.",
                "To make updates to the trip, please load the page again.",
                f"Fields which differ: {', '.join(differing_fields) or '???'}",
            ]
        )

    def form_valid(self, form):
        self._ignore_leaders_if_unchanged(form)

        trip = form.save(commit=False)
        if not trip.summary:
            trip.summary = trip.description_to_text(
                maxchars=models.Trip.summary.field.max_length
            )
        if self.update_rescinds_approval:
            trip.chair_approved = False

        trip.activity = trip.get_legacy_activity()

        # Make sure that nobody else edits the trip while doing this comparison!
        # (We do this here instead of in form `clean` so we can guarantee lock at save)
        with transaction.atomic():
            current_trip = models.Trip.objects.select_for_update().get(pk=trip.pk)

            stale_msg = self._stale_revision_message(form, current_trip, trip)
            if stale_msg:
                form.errors["__all__"] = ErrorList([stale_msg])
                return self.form_invalid(form)

            trip.last_updated_by = self.request.participant
            trip.edit_revision += 1
            return super().form_valid(form)


@dataclass(frozen=True)
class PreviousLookup:
    on_or_after_date: date | None
    date_invalid: bool
    previous_lookup_date: date | None

    def must_login_to_view_older_trips(self, request: HttpRequest) -> bool:
        if request.user.is_authenticated or self.on_or_after_date is None:
            return False
        if self.previous_lookup_date is None:
            return False
        return self.previous_lookup_date < _earliest_allowed_anon_lookback_date()


class TripListView(ListView):
    """Superclass for any view that displays a list of trips.

    To keep responses reasonably-sized, we support pagination-like behavior,
    filtering trips down to just those since some past date. One can, of
    course, select a date far in the past to get a *massive* DOM, but the
    server can easily handle reporting the 2,000+ trips.
    """

    ordering = ["trip_date", "-time_created"]

    model = models.Trip
    template_name = "trips/all/view.html"
    context_object_name = "trip_queryset"

    def _can_view_requested_trips(self) -> bool:
        if self.request.user.is_authenticated:
            return True
        start_date, _ = self._optionally_filter_from_args()
        if start_date is None:
            return True  # We'll just show upcoming trips
        return start_date >= _earliest_allowed_anon_lookback_date()

    def get_queryset(self):
        trips = super().get_queryset()
        return annotated_for_trip_list(trips)

    def _optionally_filter_from_args(self) -> tuple[date | None, bool]:
        """Return the date at which we want to omit previous trips, plus validity boolean.

        If the user passes an invalid date (for example, because they were
        manually building the query arguments), we don't want to 500 and
        instead should just give them a simple warning message.
        """
        if "after" not in self.request.GET:
            # No filtering, which is obviously valid
            return None, False

        after = self.request.GET["after"]
        try:
            start_date = date.fromisoformat(after)
        except (TypeError, ValueError):
            return None, True

        return start_date, False

    def _get_lookback_info(self) -> PreviousLookup:
        """Describe the lookup range for trip dates, control links for larger ranges."""
        on_or_after_date, date_invalid = self._optionally_filter_from_args()
        oldest_requested_trip_date = on_or_after_date or local_date()

        # Prevent rendering "Previous trips" if we know there won't be any.
        # Also prevents a weird edge case -- you can pass a date in the year 1.
        # (When the server tries to subtract 365 days, Python declines to make BCE dates)
        if oldest_requested_trip_date < FIRST_TRIP_DATE:
            previous_lookup_date = None
        else:
            # Get approximately one year prior for use in paginating back in time.
            # (need not be exact/handle leap years)
            one_year_prior = oldest_requested_trip_date - TRIPS_LOOKBACK
            if not self.request.user.is_authenticated:
                earliest_allowed = _earliest_allowed_anon_lookback_date()
                previous_lookup_date = (
                    # If we can't go back any further, we'll show a link
                    one_year_prior
                    if earliest_allowed >= oldest_requested_trip_date
                    # We shouldn't link anonymous users to a page they can't see.
                    else max(earliest_allowed, one_year_prior)
                )
            else:
                previous_lookup_date = one_year_prior

        # Sanity check -- the previous date should *always* be in the past.
        if previous_lookup_date is not None:
            assert previous_lookup_date < oldest_requested_trip_date

        return PreviousLookup(
            on_or_after_date=on_or_after_date,
            date_invalid=date_invalid,
            previous_lookup_date=previous_lookup_date,
        )

    def get_context_data(self, **kwargs):
        """Sort trips into past and present trips."""
        context = super().get_context_data(**kwargs)
        trips = context[self.context_object_name]
        today = local_date()
        context["today"] = today

        info = self._get_lookback_info()
        context["must_login_to_view_older_trips"] = info.must_login_to_view_older_trips(
            self.request
        )
        context["date_invalid"] = info.date_invalid
        context["previous_lookup_date"] = info.previous_lookup_date

        if info.on_or_after_date:
            context["on_or_after_date"] = info.on_or_after_date
            trips = trips.filter(trip_date__gte=info.on_or_after_date)

        # By default, just show upcoming trips.
        context["current_trips"] = trips.filter(trip_date__gte=today)

        # However, if we've explicitly opted in to showing past trips, include them.
        if not self._can_view_requested_trips():
            requested_url = (
                reverse("trips") + "?after=" + info.on_or_after_date.isoformat()
            )
            # URL encoding is unnecessary, but might as well use safer patterns.
            next_url = (
                reverse("account_login") + "?" + urlencode({"next": requested_url})
            )
            messages.error(
                self.request,
                f'You must <a href="{next_url}">log in to view trips</a> before {_earliest_allowed_anon_lookback_date()}.',
                extra_tags="safe",
            )
        elif info.on_or_after_date:
            # Note that we need to sort past trips in descending order (most recent trips first).
            # This is because we have a cutoff in the past, and it would display strangely to sort ascending.
            context["past_trips"] = trips.filter(trip_date__lt=today).order_by(
                "-trip_date", "-time_created"
            )
            if not info.on_or_after_date:
                # We're on the special 'all trips' view, so there are no add'l previous trips
                context["previous_lookup_date"] = None
        return context


def search_trips(
    text: str,
    filters: None | Q,
    limit: int = 100,
) -> QuerySet[models.Trip]:
    trips = models.Trip.objects.all()
    if filters:
        trips = trips.filter(filters)

    # It's valid to not provide a search term at all.
    # In this case, there's no real meaningful way to "rank" matches; put newest first.
    if not text:
        return trips.order_by("-pk")[:limit]

    query = SearchQuery(text)
    return (
        trips.annotate(
            search=models.trips_search_vector,
            rank=SearchRank(models.trips_search_vector, query),
        )
        .filter(search=text)
        .order_by("-rank")[:limit]
    )


class TripSearchView(ListView, FormView):
    form_class = forms.TripSearchForm

    model = models.Trip
    template_name = "trips/search.html"
    context_object_name = "matching_trips"

    query: str = ""
    limit: int = 100

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_valid_search"] = any(
            self.request.GET.get(field)
            for field in forms.TripSearchForm.declared_fields
        )
        context["max_results_shown"] = len(context["matching_trips"]) == self.limit
        return context

    def get_initial(self):
        """Use the querystring to populate the form."""
        return {
            label: self.request.GET.get(label, "")
            for label in self.form_class.declared_fields
        }

    def form_valid(self, form: forms.TripSearchForm) -> HttpResponseRedirect:
        """Populate successful form contents into the URL."""
        params = {
            label: form.cleaned_data[label]
            for label in form.declared_fields
            if form.cleaned_data[label]
        }
        url = reverse("search_trips")
        if params:
            url += f"?{urlencode(params)}"
        else:
            messages.error(self.request, "Specify a search query and/or some filters!")
        return redirect(url)

    def get_queryset(self) -> QuerySet[models.Trip]:
        """Return sorted trip matches based on the query and/or filters."""
        if not self.request.GET:
            return models.Trip.objects.none()

        query = self.request.GET.get("q", "")
        specified_filters = {
            field: value
            for field, value in self.request.GET.items()
            if value and field in {"winter_terrain_level", "trip_type", "program"}
        }
        return annotated_for_trip_list(
            search_trips(
                query,
                filters=Q(**specified_filters) if specified_filters else None,
                limit=self.limit,
            ),
        )

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ApproveTripsView(ListView):
    model = models.Trip
    template_name = "trips/all/manage.html"

    def get_queryset(self):
        """Filter to only *upcoming* trips needing approval, sort by those with itinerary!."""
        all_trips = super().get_queryset()
        return (
            all_trips.filter(
                activity=self.kwargs["activity"],
                trip_date__gte=local_date(),
                chair_approved=False,
            )
            .select_related("info")
            .prefetch_related("leaders", "leaders__leaderrating_set")
            .order_by(*models.Trip.ordering_for_approval)
        )

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        try:
            activity_enum = enums.Activity(kwargs.get("activity"))
        except ValueError:
            raise Http404  # noqa: B904

        if not perm_utils.is_chair(request.user, activity_enum):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _leader_emails_missing_itinerary(trips):
        now = date_utils.local_now()
        no_itinerary_trips = (trip for trip in trips if not trip.info)

        for trip in no_itinerary_trips:
            if now < date_utils.itinerary_available_at(trip.trip_date):
                continue  # Not yet able to submit!
            for leader in trip.leaders.all():
                yield leader.email_addr

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trips = list(context["object_list"])
        context["trips_needing_approval"] = trips
        context["leader_emails_missing_itinerary"] = ", ".join(
            sorted(set(self._leader_emails_missing_itinerary(trips)))
        )
        context["first_unapproved_trip"] = trips[0] if trips else None
        return context


class RunTripLotteryView(DetailView, TripLeadersOnlyView):
    model = models.Trip

    # There's no need to build in this prevention;
    # old trips will never be in lottery mode
    forbid_modifying_old_trips = False

    def get(self, request, *args, **kwargs):
        return redirect(reverse("view_trip", kwargs=self.kwargs))

    def post(self, request, *args, **kwargs):
        trip = self.get_object()
        runner = SingleTripLotteryRunner(trip)
        runner()
        return redirect(reverse("view_trip", args=(trip.pk,)))
