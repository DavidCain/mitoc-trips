"""
Views relating to leader applications.

Participants can express interest in becoming a leader for a specific activity,
and activity chairs can respond to those applications with recommendations
and/or ratings.
"""
from collections import defaultdict
from collections.abc import Iterator, Mapping

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet
from django.db.models.fields import DateField
from django.db.models.functions import Cast, Least
from django.forms.models import model_to_dict
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.views.generic import CreateView, DetailView, ListView, TemplateView, View
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import FormMixin

import ws.utils.perms as perm_utils
import ws.utils.ratings as ratings_utils
from ws import enums, forms, models
from ws.decorators import chairs_only, user_info_required
from ws.middleware import RequestWithParticipant


class LeaderApplicationMixin(ratings_utils.LeaderApplicationMixin):
    """Superclass for any view involving leader applications.

    (Either participants creating one, or chairs viewing application(s).

    In both cases, we contain the activity in the URL.
    """

    kwargs: Mapping[str, str]

    @property
    def activity_enum(self) -> enums.Activity:
        """The activity, should be verified by the dispatch method."""
        return enums.Activity(self.kwargs["activity"])

    def get_queryset(self):
        return self.joined_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["activity_enum"] = self.activity_enum
        return context


class ApplicationManager(ratings_utils.ApplicationManager, LeaderApplicationMixin):
    """Superclass for views where chairs are viewing one or more applications."""

    request: RequestWithParticipant

    @property
    def chair(self) -> models.Participant:
        """The viewing participant should be an activity chair."""
        return self.request.participant


# model is a property on LeaderApplicationMixin, but a class attribute on SingleObjectMixin
class LeaderApplyView(LeaderApplicationMixin, CreateView):  # type: ignore[misc]
    request: RequestWithParticipant

    template_name = "leaders/apply.html"
    success_url = reverse_lazy("home")
    # TODO: I'm doing some nasty with this form class.
    form_class = forms.LeaderApplicationForm  # type: ignore[assignment]

    def get_success_url(self) -> str:
        return reverse("become_leader", kwargs={"activity": self.activity_enum.value})

    def get_form_kwargs(self):
        """Pass the needed "activity" parameter for dynamic form construction."""
        kwargs = super().get_form_kwargs()
        kwargs["activity_enum"] = self.activity_enum

        # Pre-fill the most-recently held rating, if not currently active
        # (Most commonly, this occurs with the annual renewal for WS leaders)
        curr_rating = self.par.activity_rating(self.activity_enum, must_be_active=True)
        if not curr_rating:
            prev_rating = self.par.activity_rating(
                self.activity_enum, must_be_active=False
            )
            kwargs["initial"] = {"desired_rating": prev_rating}
        return kwargs

    def get_queryset(self):
        """For looking up if any recent applications have been completed."""
        applications = self.model.objects
        if self.activity_enum == enums.Activity.WINTER_SCHOOL:
            return applications.filter(year=self.application_year)
        return applications

    @property
    def par(self) -> models.Participant:
        return self.request.participant

    @property
    def application_year(self) -> int:
        return models.LeaderApplication.application_year_for_activity(
            self.activity_enum
        )

    def form_valid(self, form):
        """Link the application to the submitting participant."""
        application = form.save(commit=False)
        application.year = self.application_year
        application.participant = self.par
        rating = self.par.activity_rating(self.activity_enum, must_be_active=False)
        application.previous_rating = rating or ""
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """Get any existing application and rating."""
        context = super().get_context_data(**kwargs)

        context["activity_enum"] = self.activity_enum
        context["year"] = self.application_year
        existing = self.get_queryset().filter(participant=self.par)

        accepting_apps = models.LeaderApplication.accepting_applications(
            self.activity_enum
        )
        context["accepting_applications"] = accepting_apps

        if existing:
            app = existing.order_by("-time_created").first()
            context["application"] = app
            # TODO: Move this validation into the form/route too.
            can_apply = accepting_apps and models.LeaderApplication.can_reapply(app)
            context["can_apply"] = can_apply
        else:
            context["can_apply"] = accepting_apps

        context["climbing_form_url"] = models.ClimbingLeaderApplication.google_form_url(
            participant=self.request.participant,
            embedded=True,
        )

        return context

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        activity = kwargs.get("activity")
        try:
            activity_enum = enums.Activity(activity)
        except ValueError:  # (Not a valid activity)
            messages.error(self.request, f"{activity} is not a known activity.")
            return redirect(reverse("leaders_apply"))

        if not models.LeaderApplication.can_apply_for_activity(activity_enum):
            messages.error(
                self.request,
                f"{activity_enum.label} is not accepting leader applications",
            )
            return redirect(reverse("leaders_apply"))

        return super().dispatch(request, *args, **kwargs)


class AnyActivityLeaderApplyView(TemplateView):
    template_name = "leaders/apply_any_activity.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["activities_accepting_applications"] = [
            activity_enum
            for activity_enum in enums.Activity
            if models.LeaderApplication.can_apply_for_activity(activity_enum)
        ]
        return context


# model is a property on LeaderApplicationMixin, but a class attribute on MultipleObjectMixin
class AllLeaderApplicationsView(ApplicationManager, ListView):  # type: ignore[misc]
    context_object_name = "leader_applications"
    template_name = "chair/applications/all.html"

    def get_queryset(self):
        """Annotate each application with its number of recs & ratings."""
        return self.sorted_annotated_applications()

    @staticmethod
    def _group_applications_by_year(
        applications: list[models.LeaderApplication],
    ) -> Iterator[tuple[int, list[models.LeaderApplication]]]:
        apps_by_year = defaultdict(list)
        for app in applications:
            # num_ratings is annotated by `ApplicationManager`
            if app.num_ratings or app.archived:  # type: ignore[attr-defined]
                apps_by_year[app.year].append(app)

        for year, apps in sorted(apps_by_year.items(), reverse=True):
            sorted_by_name = sorted(apps, key=lambda app: app.participant.name)
            yield (year, sorted_by_name)

    def get_context_data(self, **kwargs):
        # Super calls DetailView's `get_context_data` so we'll manually add form
        context = super().get_context_data(**kwargs)

        apps = context["leader_applications"]
        context["num_chairs"] = len(self.activity_chairs())
        context["needs_rec"] = self.needs_rec(apps)
        context["needs_rating"] = self.needs_rating(apps)
        context["pending"] = context["needs_rating"] or context["needs_rec"]
        context["activity_enum"] = self.activity_enum
        accepting_apps = models.LeaderApplication.accepting_applications(
            self.activity_enum
        )
        context["new_applications_disabled"] = not accepting_apps

        context["apps_by_year"] = self._group_applications_by_year(apps)
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        try:
            self._activity_enum = enums.Activity(kwargs.get("activity"))
        except ValueError:
            raise Http404  # noqa: B904

        if not perm_utils.chair_or_admin(request.user, self.activity_enum):
            raise PermissionDenied
        if not models.LeaderApplication.can_apply_for_activity(self.activity_enum):
            context = {
                "missing_form": True,
                "activity_enum": self.activity_enum,
            }
            return render(request, self.template_name, context)
        return super().dispatch(request, *args, **kwargs)


# model is a property on LeaderApplicationMixin, but a class attribute on SingleObjectMixin
class ArchiveLeaderApplicationView(ApplicationManager, SingleObjectMixin, View):  # type: ignore[misc]
    def get(self, request, *args, **kwargs):
        return redirect(reverse("view_application", kwargs=kwargs))

    def post(self, request, *args, **kwargs):
        application = self.get_object()
        if application.rating_given:
            messages.error(
                request, "Cannot archive an application that received a rating!"
            )
            return redirect(reverse("view_application", kwargs=kwargs))

        application.archived = True
        application.save()
        url = reverse(
            "view_application",
            kwargs={"activity": kwargs["activity"], "pk": kwargs["pk"]},
        )
        messages.success(
            request,
            format_html(
                'Archived <a href="{}">application from {}</a>.',
                url,
                application.participant.name,
            ),
        )
        return redirect(self.get_success_url())

    def get_success_url(self) -> str:
        next_app = next(iter(self.pending_applications()), None)
        if next_app:
            app_args = (self.activity_enum.value, next_app.pk)
            return reverse("view_application", args=app_args)
        return reverse("manage_applications", args=(self.activity_enum.value,))

    @method_decorator(chairs_only())
    def dispatch(self, request, *args, **kwargs):
        try:
            self._activity_enum = enums.Activity(kwargs.get("activity"))
        except ValueError:
            raise Http404  # noqa: B904
        if not perm_utils.chair_or_admin(request.user, self.activity_enum):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


# model is a property on LeaderApplicationMixin, but a class attribute on SingleObjectMixin
class LeaderApplicationView(ApplicationManager, FormMixin, DetailView):  # type: ignore[misc]
    """Handle applications by participants to become leaders."""

    form_class = forms.ApplicationLeaderForm
    context_object_name = "application"
    template_name = "chair/applications/view.html"

    def get_success_url(self) -> str:
        """Get the next application in this queue.

        (i.e. if this was an application needing a recommendation,
        move to the next application without a recommendation)
        """
        if self.next_app:  # Set before we saved this object
            app_args = (self.activity_enum.value, self.next_app.pk)
            return reverse("view_application", args=app_args)
        return reverse("manage_applications", args=(self.activity_enum.value,))

    def get_other_apps(self):
        """Get the applications that come before and after this in the queue.

        Each "queue" is of applications that need recommendations or ratings.
        """
        ordered_apps = iter(self.pending_applications())
        prev_app = None
        for app in ordered_apps:
            if app.pk == self.object.pk:
                next_app = next(ordered_apps, None)
                break
            prev_app = app
        else:
            return None, None  # Could be from another (past) year
        last_app = app  # pylint: disable=undefined-loop-variable

        def if_valid(other_app):
            mismatch = (
                not other_app
                or bool(other_app.num_recs) != bool(last_app.num_recs)
                or bool(other_app.num_ratings) != bool(last_app.num_ratings)
            )
            return None if mismatch else other_app

        return if_valid(prev_app), if_valid(next_app)

    @property
    def par_ratings(self) -> QuerySet[models.LeaderRating]:
        return models.LeaderRating.objects.filter(
            participant=self.object.participant,
            activity=self.activity_enum.value,
        )

    def existing_rating(self) -> models.LeaderRating | None:
        return self.par_ratings.filter(active=True).first()

    def existing_rec(self) -> models.LeaderRecommendation | None:
        """Load an existing recommendation for the viewing participant."""
        return models.LeaderRecommendation.objects.filter(
            creator=self.chair,
            participant=self.object.participant,
            activity=self.activity_enum.value,
            time_created__gte=self.object.time_created,
        ).first()

    def _rating_to_prefill(self) -> str | None:
        """Return the rating that we should prefill the form with (if applicable).

        Possible return values:
        - None: We're not ready for the rating step yet.
        - Empty string: We should rate, but we have nothing to pre-fill.
        - Non-empty string: We should rate and we have a pre-filled value!
        """
        # Note that the below logic technically allows admins to weigh in with a rec.
        # Admins can break consensus, but they're not required to *declare* consensus.
        all_recs = self.get_recommendations()

        proposed_ratings = {rec.rating for rec in all_recs}

        chairs = self.activity_chairs()
        users_making_recs = {rec.creator.user for rec in all_recs}

        if set(chairs).difference(users_making_recs):
            if self.activity_enum != enums.Activity.WINTER_SCHOOL:
                return None

            # As always, Winter School is special.
            # We regard both the WS chair(s) *and* the WSC as the chairs.
            # However, only the WSC gives ratings.
            # Thus, we can be missing ratings from some "chairs" but really have WSC consensus.
            assert len(chairs) >= 3, "WSC + WS chairs fewer than 3 people!?"
            if len(users_making_recs.intersection(chairs)) < 3:
                # We're definitely missing recommendations from some of the WSC.
                return None

        if len(proposed_ratings) != 1:
            return ""  # No consensus
        return proposed_ratings.pop()

    def get_initial(self) -> dict[str, str | bool]:
        """Pre-populate the rating/recommendation form.

        This method tries to provide convenience for common scenarios:

        - activity has only 1 chair, so default to a plain rating
        - all activity chairs have made recommendations, and they agree!
        - the viewing chair wishes to revise their recommendation
        - activity chairs have different recommendations

        Each of the above scenarios has different behaviors.
        """
        # Allow for editing a given rating simply by loading an old form.
        rating = self.existing_rating()
        if rating:
            return {
                "rating": rating.rating,
                "notes": rating.notes,
                "is_recommendation": False,
            }

        rec = self.existing_rec()

        # No recommendation or rating from the viewer? Blank form.
        if not rec:
            # Recommendations only make sense with multiple chairs.
            return {"is_recommendation": len(self.activity_chairs()) > 1}

        # We may be ready to assign a rating (and we may even have a pre-fillable one)
        prefill_rating = self._rating_to_prefill()
        if prefill_rating is not None:
            return {"is_recommendation": False, "rating": prefill_rating, "notes": ""}

        # Viewer has given a recommendation, but we're still waiting on others.
        # Prefill their present recommendation, in case they want to edit it.
        return {"is_recommendation": True, "rating": rec.rating, "notes": rec.notes}

    @property
    def assigned_rating(self):
        """Return any rating given in response to this application."""
        in_future = Q(
            participant=self.object.participant,
            activity=self.activity_enum.value,
            time_created__gte=self.object.time_created,
        )
        if not hasattr(self, "_assigned_rating"):
            ratings = models.LeaderRating.objects.filter(in_future)
            self._assigned_rating = ratings.order_by("time_created").first()
        return self._assigned_rating

    @property
    def before_rating(self):
        if self.assigned_rating:
            return Q(time_created__lte=self.assigned_rating.time_created)
        return Q()

    def get_recommendations(self) -> QuerySet[models.LeaderRecommendation]:
        """Get recommendations made by leaders/chairs for this application.

        Only show recommendations that were made for this application. That is,
        don't show recommendations made before the application was created (they must
        have pertained to a previous application), or those created after a
        rating was assigned (those belong to a future application).
        """
        match = Q(
            participant=self.object.participant, activity=self.activity_enum.value
        )
        rec_after_creation = Q(time_created__gte=self.object.time_created)
        find_recs = match & self.before_rating & rec_after_creation
        recs = models.LeaderRecommendation.objects.filter(find_recs)
        return recs.select_related("creator__user")  # (User used for WSC)

    def get_feedback(self):
        """Return all feedback for the participant.

        Activity chairs see the complete history of feedback (without the normal
        "clean slate" period). The only exception is that activity chairs cannot
        see their own feedback.
        """
        return (
            models.Feedback.everything.filter(participant=self.object.participant)
            .exclude(participant=self.chair)
            .select_related("leader", "trip")
            .prefetch_related("leader__leaderrating_set")
            .annotate(
                display_date=Least("trip__trip_date", Cast("time_created", DateField()))
            )
            .order_by("-display_date")
        )

    def get_context_data(self, **kwargs):
        # Super calls DetailView's `get_context_data` so we'll manually add form
        context = super().get_context_data(**kwargs)
        assigned_rating = self.assigned_rating
        context["assigned_rating"] = assigned_rating
        context["recommendations"] = self.get_recommendations()
        context["leader_form"] = self.get_form()
        context["all_feedback"] = self.get_feedback()
        context["prev_app"], context["next_app"] = self.get_other_apps()

        participant = self.object.participant
        context["active_ratings"] = list(participant.ratings(must_be_active=True))
        context["chair_activities"] = [
            activity_enum.label
            for activity_enum in enums.Activity
            if activity_enum in perm_utils.chair_activities(participant.user)
        ]
        context["existing_rating"] = self.existing_rating()
        context["existing_rec"] = self.existing_rec()
        context["hide_recs"] = not (assigned_rating or context["existing_rec"])

        all_trips_led = self.object.participant.trips_led
        context["trips_led"] = all_trips_led.filter(
            self.before_rating, activity=self.activity_enum.value
        ).prefetch_related("leaders__leaderrating_set")
        return context

    def form_valid(self, form):
        """Save the rating as a recommendation or a binding rating."""
        # After saving, the order of applications changes
        _, self.next_app = self.get_other_apps()  # Obtain next in current order

        rating = form.save(commit=False)
        rating.creator = self.chair
        rating.participant = self.object.participant
        rating.activity = self.object.activity

        is_rec = form.cleaned_data["is_recommendation"]
        if is_rec:
            # Hack to convert the (unsaved) rating to a recommendation
            # (Both models have the exact same fields)
            rec = forms.LeaderRecommendationForm(
                model_to_dict(rating), instance=self.existing_rec()
            )
            rec.save()
        else:
            ratings_utils.deactivate_ratings(rating.participant, rating.activity)
            rating.save()

        verb = "Recommended" if is_rec else "Created"
        msg = f"{verb} {rating.rating} rating for {rating.participant.name}"
        messages.success(self.request, msg)

        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        """Create the leader's rating, redirect to other applications."""
        self.object = self.get_object()
        form = self.get_form()

        if form.is_valid():
            return self.form_valid(form)
        return self.form_invalid(form)

    @method_decorator(chairs_only())
    def dispatch(self, request, *args, **kwargs):
        """Redirect if anonymous, but deny permission if not a chair."""
        try:
            self._activity_enum = enums.Activity(kwargs["activity"])
        except ValueError:
            raise Http404  # noqa: B904

        if not perm_utils.chair_or_admin(request.user, self.activity_enum):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
