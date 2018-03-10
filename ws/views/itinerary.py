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
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView, UpdateView

from ws import forms
from ws import models
from ws.decorators import group_required
from ws.mixins import TripLeadersOnlyView
from ws.utils.dates import local_date, local_now, itinerary_available_at
import ws.utils.perms as perm_utils
from ws.utils.itinerary import get_cars


class ApprovedTripsMixin(object):
    model = models.Trip

    @property
    def activity(self):
        return self.kwargs['activity']

    def get_queryset(self):
        """ All upcoming trips of this activity type. """
        return models.Trip.objects.filter(activity=self.activity,
                                          trip_date__gte=local_date())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['activity'] = self.activity
        trips = self.get_queryset()
        context['approved_trips'] = trips.filter(chair_approved=True)
        context['unapproved_trips'] = trips.filter(chair_approved=False)
        return context


class ItineraryInfoFormMixin(object):
    def get_info_form(self, trip):
        """ Return a stripped form for read-only display.

        Drivers will be displayed separately, and the 'accuracy' checkbox
        isn't needed for display.
        """
        if not trip.info:
            return None
        info_form = forms.TripInfoForm(instance=trip.info)
        info_form.fields.pop('drivers')
        info_form.fields.pop('accurate')
        return info_form


class TripMedical(ItineraryInfoFormMixin):
    def get_trip_info(self, trip):
        participants = trip.signed_up_participants.filter(signup__on_trip=True)
        participants = participants.select_related('emergency_info')
        signups = trip.signup_set.filter(on_trip=True)
        signups = signups.select_related('participant__emergency_info')
        return {'trip': trip, 'participants': participants, 'cars': get_cars(trip),
                'info_form': self.get_info_form(trip)}


class TripItineraryView(UpdateView, TripLeadersOnlyView, ItineraryInfoFormMixin):
    """ A hybrid view for creating/editing trip info for a given trip. """
    model = models.Trip
    context_object_name = 'trip'
    template_name = 'trips/itinerary.html'
    form_class = forms.TripInfoForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['itinerary_available_at'] = itinerary_available_at(self.trip.trip_date)
        context['info_form_available'] = local_now() >= context['itinerary_available_at']
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
        on_trip = (Q(pk__in=self.trip.leaders.all()) |
                   Q(signup__in=signups))
        participants = models.Participant.objects.filter(on_trip).distinct()
        has_car_info = participants.filter(car__isnull=False)
        form.fields['drivers'].queryset = has_car_info
        return form

    def form_valid(self, form):
        if local_now() < itinerary_available_at(self.trip.trip_date):
            form.errors['__all__'] = ErrorList(["Form not yet available!"])
            return self.form_invalid(form)
        self.trip.info = form.save()
        self.trip.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('view_trip', args=(self.trip.id,))


class AllTripsMedicalView(ListView, TripMedical):
    model = models.Trip
    template_name = 'trips/all/medical.html'
    context_object_name = 'trips'

    def get_queryset(self):
        trips = super().get_queryset().order_by('trip_date')
        today = local_date()
        return trips.filter(trip_date__gte=today)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        by_trip = (self.get_trip_info(trip) for trip in self.get_queryset())
        all_trips = [(c['trip'], c['participants'], c['cars'], c['info_form'])
                     for c in by_trip]
        context_data['all_trips'] = all_trips
        return context_data

    @method_decorator(group_required('WSC', 'WIMP'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TripMedicalView(DetailView, TripLeadersOnlyView, TripMedical):
    queryset = models.Trip.objects.all()
    template_name = 'trips/medical.html'

    def get_context_data(self, **kwargs):
        """ Get a trip info form for display as readonly. """
        trip = self.get_object()
        participant = self.request.participant
        context_data = self.get_trip_info(trip)
        context_data['participants'] = trip.signed_up_participants.filter(signup__on_trip=True)
        context_data['is_trip_leader'] = perm_utils.leader_on_trip(participant, trip),
        context_data['info_form'] = self.get_info_form(trip)
        return context_data


class ChairTripView(ApprovedTripsMixin, TripMedical, DetailView):
    """ Give a view of the trip intended to let chairs approve or not.

    Will show just the important details, like leaders, description, & itinerary.
    """
    template_name = 'chair/trips/view.html'

    def get_other_trips(self):
        """ Get the trips that come before and after this trip. """
        this_trip = self.get_object()

        ordered_trips = iter(self.get_queryset().filter(chair_approved=False))
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
        context['prev_trip'], context['next_trip'] = self.get_other_trips()
        context['info_form'] = self.get_info_form(context['trip'])
        return context

    def post(self, request, *args, **kwargs):
        """ Mark the trip approved and move to the next one. """
        trip = self.get_object()
        prev_trip, next_trip = self.get_other_trips()  # Do this before saving trip
        trip.chair_approved = True
        trip.save()
        if next_trip:
            return redirect(reverse('view_trip_for_approval', args=(self.activity, next_trip.id,)))
        else:
            return redirect(reverse('manage_trips', args=(self.activity,)))

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        if not perm_utils.is_chair(request.user, trip.activity):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
