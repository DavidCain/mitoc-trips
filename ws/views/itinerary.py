"""
Views relating to a trip's itinerary management, & medical information.

Each official trip should have an itinerary completed by trip leaders.
That itinerary specifies who (if anybody) will be driving for the trip,
what the intended route will be, when to worry, and more.
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.forms.utils import ErrorList
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView, UpdateView

import ws.utils.perms as perm_utils
from ws import forms, models, wimp
from ws.decorators import group_required
from ws.mixins import TripLeadersOnlyView
from ws.utils.dates import itinerary_available_at, local_date, local_now


class TripItineraryView(UpdateView, TripLeadersOnlyView):
    """A hybrid view for creating/editing trip info for a given trip."""

    model = models.Trip
    context_object_name = 'trip'
    template_name = 'trips/itinerary.html'
    form_class = forms.TripInfoForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        trip = context['trip']
        context['itinerary_available_at'] = itinerary_available_at(trip.trip_date)
        context['info_form_editable'] = trip.info_editable
        if local_now() < context['itinerary_available_at']:
            context['waiting_to_open'] = True
            context['form'].fields.pop('accurate')
            for field in context['form'].fields.values():
                field.disabled = True
        return context

    def get_initial(self):
        self.trip = self.object  # Form instance will become object
        return {'trip': self.trip}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.trip.info
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        signups = self.trip.signup_set.filter(on_trip=True)
        on_trip = Q(pk__in=self.trip.leaders.all()) | Q(signup__in=signups)
        participants = models.Participant.objects.filter(on_trip).distinct()
        has_car_info = participants.filter(car__isnull=False)
        form.fields['drivers'].queryset = has_car_info
        return form

    def form_valid(self, form):
        if not self.trip.info_editable:
            verb = "modified" if self.trip.info else "created"
            form.errors['__all__'] = ErrorList([f"Itinerary cannot be {verb}"])
            return self.form_invalid(form)
        self.trip.info = form.save()
        self.trip.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('view_trip', args=(self.trip.pk,))


class AllTripsMedicalView(ListView):
    model = models.Trip
    template_name = 'trips/all/medical.html'
    context_object_name = 'trips'

    def get_queryset(self):
        trips = super().get_queryset().order_by('trip_date')
        today = local_date()
        return trips.filter(trip_date__gte=today)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        context_data['wimps'] = wimp.active_wimps()
        return context_data

    @method_decorator(group_required('WSC', 'WIMP'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TripMedicalView(DetailView):
    model = models.Trip
    template_name = 'trips/medical.html'

    @staticmethod
    def _can_view(trip, request):
        """Leaders, chairs, and a trip WIMP can view this page."""
        return (
            perm_utils.in_any_group(request.user, ['WIMP'])
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
            return render(request, 'not_your_trip.html', {'trip': trip})
        return normal_response

    def get_context_data(self, **kwargs):
        """Get a trip info form for display as readonly."""
        context_data = super().get_context_data(**kwargs)
        trip = self.object
        participant = self.request.participant
        context_data['is_trip_leader'] = perm_utils.leader_on_trip(participant, trip)

        return context_data


class ChairTripView(DetailView):
    """Give a view of the trip intended to let chairs approve or not.

    Will show just the important details, like leaders, description, & itinerary.
    """

    model = models.Trip
    template_name = 'chair/trips/view.html'

    @property
    def activity(self):
        return self.kwargs['activity']

    def get_queryset(self):
        """All trips of this activity type.

        For identifying only trips that need attention, callers
        should probably also filter on `trip_date` and `chair_approved`.

        By declining to filter here, this prevents a 404 on past trips.
        (In other words, a trip in the past that may or may not have been
        approved can still be viewed as it would have been for activity chairs)
        """
        # Order by the same ordering that's given on the "Trips needing approval" table
        return models.Trip.objects.filter(activity=self.activity).order_by(
            *models.Trip.ordering_for_approval
        )

    def get_other_trips(self):
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['activity'] = self.activity

        # Provide buttons for quick navigation between upcoming trips needing approval
        context['prev_trip'], context['next_trip'] = self.get_other_trips()
        return context

    def post(self, request, *args, **kwargs):
        """Mark the trip approved and move to the next one, if any."""
        trip = self.get_object()
        _, next_trip = self.get_other_trips()  # Do this before saving trip
        trip.chair_approved = True
        trip.save()
        if next_trip:
            return redirect(
                reverse('view_trip_for_approval', args=(self.activity, next_trip.id))
            )
        return redirect(reverse('manage_trips', args=(self.activity,)))

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        if not perm_utils.is_chair(request.user, trip.required_activity_enum()):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
