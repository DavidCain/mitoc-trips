"""
Trip views.

A "trip" is any official trip registered in the system - created by leaders, to be
attended by any interested participants.
"""
from collections import defaultdict
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

import ws.utils.perms as perm_utils
import ws.utils.signups as signup_utils
from ws import forms, models
from ws.decorators import group_required
from ws.lottery.run import SingleTripLotteryRunner
from ws.mixins import TripLeadersOnlyView
from ws.templatetags.trip_tags import annotated_for_trip_list
from ws.utils.dates import date_from_iso, is_winter_school, local_date
from ws.utils.geardb import outstanding_items


class TripView(DetailView):
    """ Display the trip to both unregistered users and known participants.

    For unregistered users, the page will have minimal information (a description,
    and leader names). For other participants, the controls displayed to them
    will vary depending on their permissions.
    """

    model = models.Trip
    context_object_name = 'trip'
    template_name = 'trips/view.html'

    def get_queryset(self):
        trips = super().get_queryset().select_related('info')
        return trips.prefetch_related('leaders', 'leaders__leaderrating_set')

    def get_participant_signup(self, trip=None):
        """ Return viewer's signup for this trip (if one exists, else None) """
        if not self.request.participant:
            return None
        trip = trip or self.get_object()
        return self.request.participant.signup_set.filter(trip=trip).first()

    @staticmethod
    def rentals_by_participant(trip):
        """ Yield all items rented by leaders & participants on this trip. """
        on_trip = trip.signup_set.filter(on_trip=True).select_related('participant')
        trip_participants = [s.participant for s in on_trip]
        leaders = [leader for leader in trip.leaders.all()]

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
        for item in outstanding_items(
            participant_by_email, rented_on_or_before=trip.trip_date
        ):
            participant = participant_by_email[item['email']]
            gear_per_participant[participant].append(item)

        # Yield in order of leaders & default signup ordering
        for par in leaders + trip_participants:
            if par in gear_per_participant:
                yield par, gear_per_participant[par]

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        trip = self.object

        context['leader_on_trip'] = perm_utils.leader_on_trip(
            self.request.participant, trip, True
        )
        context['can_admin'] = context['leader_on_trip'] or perm_utils.chair_or_admin(
            self.request.user, trip.activity
        )
        if context['can_admin'] or perm_utils.is_leader(self.request.user):
            context['rentals_by_par'] = list(self.rentals_by_participant(trip))
        return context

    def post(self, request, *args, **kwargs):
        """ Add signup to trip or waitlist, if applicable.

        Used if the participant has signed up, but wasn't placed.
        """
        signup = self.get_participant_signup()
        signup_utils.trip_or_wait(signup, self.request, trip_must_be_open=True)
        return self.get(request)


class ReviewTripView(DetailView):
    model = models.Trip
    template_name = 'trips/review.html'
    success_msg = "Thanks for your feedback!"

    @property
    def posted_feedback(self):
        """ Convert named fields of POST data to participant -> feedback mapping.

        If the form data was garbled (intentionally or otherwise), this method
        will raise ValueError or TypeError (on either 'split' or `int`)
        """
        for key, comments in self.request.POST.items():
            if not (key.startswith("par_") or key.startswith("flake_")):
                continue

            feedback_type, par_pk = key.split('_')
            showed_up = feedback_type == 'par'

            yield int(par_pk), comments.strip(), showed_up

    def post(self, request, *args, **kwargs):
        """ Create or update all feedback passed along in form data. """
        trip = self.object = self.get_object()
        if trip.feedback_window_passed:
            messages.warning(
                self.request,
                "Trip feedback window has passed. " "Feedback may not be updated.",
            )
            return redirect(reverse('review_trip', args=(trip.pk,)))

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
            existing = feedback = existing_feedback.get(pk)

            if existing and blank_feedback:
                existing.delete()
                continue

            if not existing:
                if blank_feedback:
                    continue  # Don't create new feedback saying nothing useful
                kwargs = {
                    'leader': leader,
                    'trip': trip,
                    'participant': models.Participant.objects.get(pk=pk),
                }
                feedback = models.Feedback.objects.create(**kwargs)

            feedback.comments = comments
            feedback.showed_up = showed_up
            feedback.save()

        messages.success(self.request, self.success_msg)
        return redirect(reverse('home'))

    @property
    def trip_participants(self):
        accepted_signups = self.object.signup_set.filter(on_trip=True)
        accepted_signups = accepted_signups.select_related('participant')
        return [signup.participant for signup in accepted_signups]

    def get_existing_feedback(self):
        leader = self.request.participant
        return models.Feedback.everything.filter(trip=self.object, leader=leader)

    @property
    def feedback_list(self):
        feedback = self.get_existing_feedback()
        par_comments = dict(feedback.values_list('participant__pk', 'comments'))
        return [(par, par_comments.get(par.pk, '')) for par in self.trip_participants]

    def get_context_data(self, **kwargs):
        today = local_date()
        trip = self.object = self.get_object()
        return {
            "trip": trip,
            "feedback_window_passed": trip.feedback_window_passed,
            "trip_completed": today >= trip.trip_date,
            "feedback_required": trip.activity == 'winter_school',
            "feedback_list": self.feedback_list,
        }

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        if not perm_utils.leader_on_trip(request.participant, trip, False):
            return render(request, 'not_your_trip.html', {'trip': trip})
        return super().dispatch(request, *args, **kwargs)


class CreateTripView(CreateView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = 'trips/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial'] = kwargs.get('initial', {})
        if not self.request.user.is_superuser:
            allowed_activities = self.request.participant.allowed_activities
            kwargs['allowed_activities'] = allowed_activities

            if is_winter_school() and 'winter_school' in allowed_activities:
                kwargs['initial']['activity'] = 'winter_school'
            else:
                # The first activity may not be open to the leader.
                # We restrict choices, so ensure leader can lead this activity.
                kwargs['initial']['activity'] = kwargs['allowed_activities'][0]
        return kwargs

    def get_success_url(self):
        return reverse('view_trip', args=(self.object.pk,))

    def get_initial(self):
        """ Default with trip creator among leaders. """
        initial = super().get_initial().copy()
        # It's possible for WSC to create trips while not being a leader
        if perm_utils.is_leader(self.request.user):
            initial['leaders'] = [self.request.participant]
        return initial

    def form_valid(self, form):
        """ After is_valid(), assign creator from User, add empty waitlist. """
        creator = self.request.participant
        trip = form.save(commit=False)
        trip.creator = creator
        return super().form_valid(form)

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class DeleteTripView(DeleteView, TripLeadersOnlyView):
    model = models.Trip
    success_url = reverse_lazy('upcoming_trips')

    def get(self, request, *args, **kwargs):
        """ Request is valid, but method is not (use POST). """
        messages.warning(self.request, "Use delete button to remove trips.")
        return redirect(reverse('view_trip', kwargs=self.kwargs))


class EditTripView(UpdateView, TripLeadersOnlyView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = 'trips/edit.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not self.request.user.is_superuser:
            allowed_activities = self.request.participant.allowed_activities
            kwargs['allowed_activities'] = allowed_activities
        return kwargs

    @property
    def update_rescinds_approval(self):
        trip = self.object
        return (
            trip.chair_approved
            and not perm_utils.is_chair(self.request.user, trip.activity)
            and trip.trip_date >= local_date()  # Doesn't matter after trip
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['update_rescinds_approval'] = self.update_rescinds_approval
        return context

    def get_success_url(self):
        return reverse('view_trip', args=(self.object.pk,))

    def _ignore_leaders_if_unchanged(self, form):
        """ Don't update the leaders m2m field if unchanged.

        This is a hack to avoid updating the m2m set (normally cleared, then
        reset) Without this, post_add (signal used to send emails) will send
        out a message to all leaders on _every_ trip update.

        A compromise: Only send emails when the leader list is changed.
        See ticket 6707 for an eventual fix to this behavior
        """
        old_pks = {leader.pk for leader in self.object.leaders.all()}
        new_pks = {leader.pk for leader in form.cleaned_data['leaders']}
        if not old_pks.symmetric_difference(new_pks):
            form.cleaned_data.pop('leaders')

    def form_valid(self, form):
        self._ignore_leaders_if_unchanged(form)

        if self.update_rescinds_approval:
            trip = form.save(commit=False)
            trip.chair_approved = False
        return super().form_valid(form)


class TripListView(ListView):
    """ Superclass for any view that displays a list of trips.

    We support loading and displaying all trips (`/trips/all`). The SQL query
    is pretty efficient, though it results in a pretty large DOM for clients
    (since we have over 1,000 trips).

    To keep responses reasonably-sized, we support pagination-like behavior,
    filtering trips down to just those since some past date.
    """

    model = models.Trip
    template_name = 'trips/all/view.html'
    context_object_name = 'trip_queryset'
    include_past_trips = True

    def get_queryset(self):
        trips = super().get_queryset()
        return annotated_for_trip_list(trips)

    def _optionally_filter_from_args(self):
        """ Return the date at which we want to omit previous trips, plus validity boolean.

        If the user passes an invalid date (for example, because they were
        manually building the query arguments), we don't want to 500 and
        instead should just give them a simple warning message.
        """
        start_date = None
        start_date_invalid = False
        if 'after' in self.request.GET:
            after = self.request.GET['after']
            try:
                start_date = date_from_iso(after)
            except (TypeError, ValueError):
                start_date_invalid = True
            else:
                start_date_invalid = False

        return (start_date, start_date_invalid)

    def get_context_data(self, **kwargs):
        """ Sort trips into past and present trips. """
        context = super().get_context_data(**kwargs)
        trips = context[self.context_object_name]
        today = local_date()
        context['today'] = today

        on_or_after_date, context['date_invalid'] = self._optionally_filter_from_args()
        if on_or_after_date:
            context['on_or_after_date'] = on_or_after_date
            trips = trips.filter(trip_date__gte=on_or_after_date)

        # Get approximately one year prior for use in paginating back in time.
        # (need not be exact/handle leap years)
        context['one_year_prior'] = (on_or_after_date or today) - timedelta(days=365)

        # By default, just show upcoming trips.
        context['current_trips'] = trips.filter(trip_date__gte=today)
        # However, if we've explicitly opted in to showing past trips, include them
        if self.include_past_trips or on_or_after_date:
            context['past_trips'] = trips.filter(trip_date__lt=today)
            if not on_or_after_date:
                # We're on the special 'all trips' view, so there are no add'l previous trips
                context['one_year_prior'] = None
        return context


class UpcomingTripsView(TripListView):
    """ By default, view only upcoming (future) trips.

    If given a date, filter to only trips after that date.
    """

    # Default value, but past trips can appear by including a date filter
    include_past_trips = False


class AllTripsView(TripListView):
    """ View all trips, past and present (optionally after a given date). """

    include_past_trips = True


class ApproveTripsView(UpcomingTripsView):
    template_name = 'trips/all/manage.html'

    def get_queryset(self):
        upcoming_trips = super().get_queryset()
        return upcoming_trips.filter(activity=self.kwargs['activity'])

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        activity = kwargs.get('activity')
        if not perm_utils.is_chair(request.user, activity):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # No point sorting into current, past (queryset already handles)
        context = super().get_context_data(**kwargs)
        unapproved_trips = self.get_queryset().filter(chair_approved=False)
        context['first_unapproved_trip'] = unapproved_trips.first()
        return context


class RunTripLotteryView(DetailView, TripLeadersOnlyView):
    model = models.Trip

    def get(self, request, *args, **kwargs):
        return redirect(reverse('view_trip', kwargs=self.kwargs))

    def post(self, request, *args, **kwargs):
        trip = self.get_object()
        runner = SingleTripLotteryRunner(trip)
        runner()
        return redirect(reverse('view_trip', args=(trip.pk,)))
