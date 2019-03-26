"""
Views relating to leader management.

Any participant in the system can be granted ratings in one or more activities,
which will entitle them to create trips, view participant information, and more.

For views relating to the leader application process, see ws.views.applications
"""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Max
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, ListView, View

import ws.utils.perms as perm_utils
import ws.utils.ratings as ratings_utils
from ws import forms, models
from ws.decorators import chairs_only, group_required


class AllLeadersView(ListView):
    model = models.Participant
    context_object_name = 'leaders'
    template_name = 'leaders/all.html'

    def get_queryset(self):
        """ Returns all leaders with active ratings. """
        return models.Participant.leaders.get_queryset()

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        closed_activities = models.LeaderRating.CLOSED_ACTIVITY_CHOICES
        activities = [
            (val, label) for (val, label) in closed_activities if val != 'cabin'
        ]
        context_data['activities'] = activities
        return context_data

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class CreateRatingView(CreateView):
    """ Should be inhereted to provide a template. """

    form_class = forms.LeaderForm

    @property
    def allowed_activities(self):
        return perm_utils.chair_activities(self.request.user, True)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['allowed_activities'] = self.allowed_activities
        return kwargs

    def form_valid(self, form):
        """ Ensure the leader can assign ratings, then apply assigned rating.

        Any existing ratings for this activity will be marked as inactive.
        """
        activity = form.cleaned_data['activity']
        participant = form.cleaned_data['participant']

        # Sanity check on ratings (form hides dissallowed activities)
        if not perm_utils.is_chair(self.request.user, activity, True):
            not_chair = "You cannot assign {} ratings".format(activity)
            form.add_error("activity", not_chair)
            return self.form_invalid(form)

        ratings_utils.deactivate_ratings(participant, activity)

        rating = form.save(commit=False)
        rating.creator = self.request.participant

        msg = "Gave {} rating of '{}'".format(participant, rating.rating)
        messages.success(self.request, msg)
        return super().form_valid(form)


class OnlyForActivityChair(View):
    @property
    def activity(self):
        """ The activity, should be verified by the dispatch method. """
        return self.kwargs['activity']

    @method_decorator(chairs_only())
    def dispatch(self, request, *args, **kwargs):
        activity = kwargs.get('activity')
        if not perm_utils.chair_or_admin(request.user, activity):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('activity_leaders', args=(self.activity,))


class DeactivateLeaderRatingsView(OnlyForActivityChair):
    def _success(self):
        return redirect(self.get_success_url())

    def get(self, request, *args, **kwargs):
        return self._success()

    def post(self, request, *args, **kwargs):
        rating_pks = request.POST.getlist('deactivate', [])
        if not rating_pks:
            return self._success()
        ratings = models.LeaderRating.objects.filter(pk__in=rating_pks)
        ratings = ratings.select_related('participant')
        if any(r.activity != self.activity for r in ratings):
            # The route is only for deactivating ratings for one activity
            # (an activity for which the requester is a chair)
            raise PermissionDenied

        # Iterate each rating and save individually
        # (Not the most efficient, but in enables leader management signals)
        for rating in ratings:
            rating.active = False
            rating.save()  # Do a single update (not bulk) to trigger signals
        removed_names = ', '.join(rating.participant.name for rating in ratings)
        msg = "Removed {} rating for {}".format(self.activity, removed_names)
        messages.success(request, msg)
        return self._success()


class ActivityLeadersView(OnlyForActivityChair, CreateRatingView):
    """ Manage the leaders of a single activity. """

    template_name = 'leaders/by_activity.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['hide_activity'] = True
        return kwargs

    def get_initial(self):
        initial = super().get_initial().copy()
        initial['activity'] = self.activity
        return initial

    def get_ratings(self):
        """ Returns all leaders with active ratings. """
        ratings = models.LeaderRating.objects.filter(
            activity=self.activity, active=True
        )
        ratings = ratings.prefetch_related('participant__trips_led')
        return ratings.annotate(last_trip_date=Max('participant__trips_led__trip_date'))

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['activity'] = self.activity
        context_data['ratings'] = self.get_ratings()
        return context_data


class ManageLeadersView(CreateRatingView):
    """ A view to update the rating of any leader across all ratings. """

    form_class = forms.LeaderForm
    template_name = 'chair/leaders.html'
    success_url = reverse_lazy('manage_leaders')

    @method_decorator(chairs_only())
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
