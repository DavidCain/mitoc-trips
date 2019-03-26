"""
Views relating to leader applications.

Participants can express interest in becoming a leader for a specific activity,
and activity chairs can respond to those applications with recommendations
and/or ratings.
"""
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.fields import DateField
from django.db.models.functions import Cast, Least
from django.forms.models import model_to_dict
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView, ListView
from django.views.generic.edit import FormMixin

import ws.utils.perms as perm_utils
import ws.utils.ratings as ratings_utils
from ws import forms, models
from ws.decorators import chairs_only, user_info_required


class LeaderApplicationMixin(ratings_utils.LeaderApplicationMixin):
    """ Superclass for any view involving leader applications.

    (Either participants creating one, or chairs viewing application(s).

    In both cases, we contain the activity in the URL.
    """

    @property
    def activity(self):
        """ The activity, should be verified by the dispatch method. """
        return self.kwargs['activity']

    def get_queryset(self):
        return self.joined_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['activity'] = self.activity
        return context


class ApplicationManager(ratings_utils.ApplicationManager, LeaderApplicationMixin):
    """ Superclass for views where chairs are viewing one or more applications. """

    @property
    def chair(self):
        """ The viewing participant should be an activity chair. """
        return self.request.participant


class LeaderApplyView(LeaderApplicationMixin, CreateView):
    template_name = "leaders/apply.html"
    success_url = reverse_lazy('home')
    form_class = forms.LeaderApplicationForm

    def get_success_url(self):
        return reverse('become_leader', kwargs={'activity': self.activity})

    def get_form_kwargs(self):
        """ Pass the needed "activity" parameter for dynamic form construction. """
        kwargs = super().get_form_kwargs()
        kwargs['activity'] = self.activity

        # Pre-fill the most-recently held rating, if not currently active
        # (Most commonly, this occurs with the annual renewal for WS leaders)
        curr_rating = self.par.activity_rating(self.activity, rating_active=True)
        prev_rating = self.par.activity_rating(self.activity, rating_active=False)
        if not curr_rating:
            kwargs['initial'] = {'desired_rating': prev_rating}
        return kwargs

    def get_queryset(self):
        """ For looking up if any recent applications have been completed. """
        applications = self.model.objects
        if self.activity == models.LeaderRating.WINTER_SCHOOL:
            return applications.filter(year=self.application_year)
        return applications

    @property
    def par(self):
        return self.request.participant

    def form_valid(self, form):
        """ Link the application to the submitting participant. """
        application = form.save(commit=False)
        application.year = self.application_year
        application.participant = self.par
        rating = self.par.activity_rating(self.activity, rating_active=False)
        application.previous_rating = rating or ''
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """ Get any existing application and rating. """
        context = super().get_context_data(**kwargs)

        context['year'] = self.application_year
        existing = self.get_queryset().filter(participant=self.par)
        if existing:
            app = existing.order_by('-time_created').first()
            context['application'] = app
            context['can_apply'] = self.can_reapply(app)
        else:
            context['can_apply'] = True
        return context

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        if not models.LeaderApplication.can_apply(kwargs.get('activity')):
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class AllLeaderApplicationsView(ApplicationManager, ListView):
    context_object_name = 'leader_applications'
    template_name = 'chair/applications/all.html'

    def get_queryset(self):
        """ Annotate each application with its number of recs & ratings. """
        return self.sorted_annotated_applications()

    def _group_applications_by_year(self, applications):
        apps_by_year = defaultdict(list)
        for app in applications:
            if app.num_ratings:
                apps_by_year[app.year].append(app)

        for year, apps in sorted(apps_by_year.items(), reverse=True):
            sorted_by_name = sorted(apps, key=lambda app: app.participant.name)
            yield (year, sorted_by_name)

    def get_context_data(self, **kwargs):
        # Super calls DetailView's `get_context_data` so we'll manually add form
        context = super().get_context_data(**kwargs)

        apps = context['leader_applications']
        context['num_chairs'] = self.num_chairs
        context['needs_rec'] = self.needs_rec(apps)
        context['needs_rating'] = self.needs_rating(apps)
        context['pending'] = context['needs_rating'] or context['needs_rec']

        context['apps_by_year'] = self._group_applications_by_year(apps)
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        activity = kwargs.get('activity')
        if not perm_utils.chair_or_admin(request.user, activity):
            raise PermissionDenied
        if not models.LeaderApplication.can_apply(self.activity):
            context = {'missing_form': True, 'activity': self.activity}
            return render(request, self.template_name, context)
        return super().dispatch(request, *args, **kwargs)


class LeaderApplicationView(ApplicationManager, FormMixin, DetailView):
    """ Handle applications by participants to become leaders. """

    form_class = forms.ApplicationLeaderForm
    context_object_name = 'application'
    template_name = 'chair/applications/view.html'

    def get_success_url(self):
        """ Get the next application in this queue.

        (i.e. if this was an application needing a recommendation,
        move to the next application without a recommendation)
        """
        if self.next_app:  # Set before we saved this object
            app_args = (self.activity, self.next_app.pk)
            return reverse('view_application', args=app_args)
        else:
            return reverse('manage_applications', args=(self.activity,))

    def get_other_apps(self):
        """ Get the applications that come before and after this in the queue.

        Each "queue" is of applications that need recommendations or ratings.
        """
        ordered_apps = iter(self.pending_applications())
        prev_app = None
        for app in ordered_apps:
            if app.pk == self.object.pk:
                try:
                    next_app = next(ordered_apps)
                except StopIteration:
                    next_app = None
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
    def par_ratings(self):
        find_ratings = Q(participant=self.object.participant, activity=self.activity)
        return models.LeaderRating.objects.filter(find_ratings)

    @property
    def existing_rating(self):
        return self.par_ratings.filter(active=True).first()

    @property
    def existing_rec(self):
        """ Load an existing recommendation for the viewing participant. """
        if not hasattr(self, '_existing_rec'):
            find_rec = Q(
                creator=self.chair,
                participant=self.object.participant,
                activity=self.activity,
                time_created__gte=self.object.time_created,
            )
            self._existing_rec = models.LeaderRecommendation.objects.filter(
                find_rec
            ).first()
        return self._existing_rec

    def default_to_recommendation(self):
        """ Whether to default the form to a recommendation or not. """
        return False if self.num_chairs < 2 else not self.existing_rec

    def get_initial(self):
        """ Load an existing rating if one exists.

        Because these applications are supposed to be done with leaders that
        have no active rating in the activity, this should almost always be
        blank.
        """
        initial = {'recommendation': self.default_to_recommendation()}
        existing = self.existing_rating or self.existing_rec
        if existing:
            initial['rating'] = existing.rating
            initial['notes'] = existing.notes
        return initial

    @property
    def assigned_rating(self):
        """ Return any rating given in response to this application. """
        in_future = Q(
            participant=self.object.participant,
            activity=self.activity,
            time_created__gte=self.object.time_created,
        )
        if not hasattr(self, '_assigned_rating'):
            ratings = models.LeaderRating.objects.filter(in_future)
            self._assigned_rating = ratings.order_by('time_created').first()
        return self._assigned_rating

    @property
    def before_rating(self):
        if self.assigned_rating:
            return Q(time_created__lte=self.assigned_rating.time_created)
        else:
            return Q()

    def get_recommendations(self, assigned_rating=None):
        """ Get recommendations made by leaders/chairs for this application.

        Only show recommendations that were made for this application. That is,
        don't show recommendations made before the application was created (they must
        have pertained to a previous application), or those created after a
        rating was assigned (those belong to a future application).
        """
        match = Q(participant=self.object.participant, activity=self.activity)
        rec_after_creation = Q(time_created__gte=self.object.time_created)
        find_recs = match & self.before_rating & rec_after_creation
        recs = models.LeaderRecommendation.objects.filter(find_recs)
        return recs.select_related('creator')

    def get_feedback(self):
        """ Return all feedback for the participant.

        Activity chairs see the complete history of feedback (without the normal
        "clean slate" period). The only exception is that activity chairs cannot
        see their own feedback.
        """
        return (
            models.Feedback.everything.filter(participant=self.object.participant)
            .exclude(participant=self.chair)
            .select_related('leader', 'trip')
            .prefetch_related('leader__leaderrating_set')
            .annotate(
                display_date=Least('trip__trip_date', Cast('time_created', DateField()))
            )
            .order_by('-display_date')
        )

    def get_context_data(self, **kwargs):
        # Super calls DetailView's `get_context_data` so we'll manually add form
        context = super().get_context_data(**kwargs)
        assigned_rating = self.assigned_rating
        context['assigned_rating'] = assigned_rating
        context['recommendations'] = self.get_recommendations(assigned_rating)
        context['leader_form'] = self.get_form()
        context['all_feedback'] = self.get_feedback()
        context['prev_app'], context['next_app'] = self.get_other_apps()

        participant = self.object.participant
        context['active_ratings'] = list(participant.ratings(rating_active=True))
        participant_chair_activities = set(
            perm_utils.chair_activities(participant.user)
        )
        context['chair_activities'] = [
            label
            for (activity, label) in models.LeaderRating.ACTIVITY_CHOICES
            if activity in participant_chair_activities
        ]
        context['existing_rating'] = self.existing_rating
        context['existing_rec'] = self.existing_rec
        context['hide_recs'] = not (assigned_rating or context['existing_rec'])

        all_trips_led = self.object.participant.trips_led
        trips_led = all_trips_led.filter(self.before_rating, activity=self.activity)
        context['trips_led'] = trips_led.prefetch_related('leaders__leaderrating_set')
        return context

    def form_valid(self, form):
        """ Save the rating as a recommendation or a binding rating. """
        # After saving, the order of applications changes
        _, self.next_app = self.get_other_apps()  # Obtain next in current order

        rating = form.save(commit=False)
        rating.creator = self.chair
        rating.participant = self.object.participant
        rating.activity = self.object.activity

        is_rec = form.cleaned_data['recommendation']
        if is_rec:
            # Hack to convert the (unsaved) rating to a recommendation
            # (Both models have the exact same fields)
            rec = forms.LeaderRecommendationForm(
                model_to_dict(rating), instance=self.existing_rec
            )
            rec.save()
        else:
            ratings_utils.deactivate_ratings(rating.participant, rating.activity)
            rating.save()

        fmt = {
            'verb': "Recommended" if is_rec else "Created",
            'rating': rating.rating,
            'participant': rating.participant.name,
        }
        msg = "{verb} {rating} rating for {participant}".format(**fmt)
        messages.success(self.request, msg)

        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        """ Create the leader's rating, redirect to other applications. """
        self.object = self.get_object()
        form = self.get_form()

        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @method_decorator(chairs_only())
    def dispatch(self, request, *args, **kwargs):
        """ Redirect if anonymous, but deny permission if not a chair. """
        if not perm_utils.chair_or_admin(request.user, self.activity):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
