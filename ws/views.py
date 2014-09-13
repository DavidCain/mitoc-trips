from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import modelformset_factory
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.generic import CreateView
from django.views.generic import DetailView
from django.views.generic import View

from ws import forms
from ws import models
from ws.decorators import group_required


class UpdateParticipantView(View):
    # The Participant and EmergencyContact are both Person models, have
    # conflicting names. Use prefixes to keep them distinct in POST data
    par_prefix = "participant"
    e_prefix = "emergency_contact"

    template_name = 'update_info.html'
    update_msg = 'Personal information updated successfully'

    def _has_car(self, request):
        return 'has_car' in request.POST

    def _participant(self, request):
        try:
            return request.user.participant
        except ObjectDoesNotExist:
            return None

    def _get_forms(self, request):
        """ Return a dictionary of forms to be passed for template rendering

        Outputs three types of forms:
            - Bound forms, if POSTed
            - Empty forms if GET, and no stored Participant data
            - Filled forms if GET, and Participant data exists

        Forms are bound to model instances for UPDATE if such instances exist.
        """
        post = request.POST if request.method == "POST" else None
        participant = self._participant(request)

        # Access other models within participant
        car = participant and participant.car
        e_info = participant and participant.emergency_info
        e_contact = e_info and e_info.emergency_contact

        # If no Participant object, fill at least with User email
        par_kwargs = {"prefix": self.par_prefix, "instance": participant}
        if not participant:
            par_kwargs["initial"] = {'email': request.user.email}

        form_dict = {
            'participant_form':  forms.ParticipantForm(post, **par_kwargs),
            'car_form': forms.CarForm(post, instance=car),
            'emergency_info_form':  forms.EmergencyInfoForm(post, instance=e_info),
            'emergency_contact_form':  forms.EmergencyContactForm(post, prefix=self.e_prefix, instance=e_contact),
        }
        return form_dict

    def get(self, request, *args, **kwargs):
        form_dict = self._get_forms(request)
        return render(request, self.template_name, form_dict)

    def post(self, request, *args, **kwargs):
        form_dict = self._get_forms(request)
        required_dict = form_dict.copy()

        if not self._has_car(request):
            required_dict.pop('car_form')

        if all(form.is_valid() for form in required_dict.values()):
            self._save_forms(request.user, required_dict)
            messages.add_message(request, messages.SUCCESS, self.update_msg)
            return redirect('/accounts/')
        else:
            # TODO: If POST fails, "this is required" displays on all car fields
            return render(request, self.template_name, form_dict)

    def _save_forms(self, user, post_forms):
        """ Given completed, validated forms, handle saving all.

        If no CarForm is supplied, a participant's existing car will be removed.

        :param post_forms: Dictionary of <template_name>: <form>
        """
        e_contact = post_forms['emergency_contact_form'].save()
        e_info = post_forms['emergency_info_form'].save(commit=False)
        e_info.emergency_contact = e_contact
        e_info = post_forms['emergency_info_form'].save()

        participant = post_forms['participant_form'].save(commit=False)
        participant.user = user
        participant.emergency_info = e_info
        try:
            car = post_forms['car_form'].save()
        except KeyError:  # No CarForm posted
            # If the Participant already existed and has a stored Car, delete it
            if participant.car:
                participant.car.delete()
                participant.car = None
        else:
            participant.car = car
        participant.save()

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(UpdateParticipantView, self).dispatch(request, *args, **kwargs)


class ParticipantDetailView(DetailView):
    queryset = models.Participant.objects.all()
    context_object_name = 'participant'
    template_name = 'participant_detail.html'

    def get_context_data(self, **kwargs):
        # By default, this method just returns a context with the object
        # However, I couldn't easily display a read-only summary of the model
        # So, this is the hackish solution
        participant = self.get_object()
        e_info = participant.emergency_info
        e_contact = e_info.emergency_contact
        context = {'participant_form': forms.ParticipantForm(instance=participant),
                   'emergency_info_form':  forms.EmergencyInfoForm(instance=e_info),
                   'emergency_contact_form':  forms.EmergencyContactForm(instance=e_contact),
                   }
        if participant.car:
            context['car_form'] = forms.CarForm(instance=participant.car)
        return context

    #@method_decorator(permission_required('ws.can_view_participant',
    #                                      raise_exception=True))
    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(ParticipantDetailView, self).dispatch(request, *args, **kwargs)


class TripDetailView(DetailView):
    queryset = models.Trip.objects.all()
    context_object_name = 'trip'
    template_name = 'trip_detail.html'

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripDetailView, self).dispatch(request, *args, **kwargs)


@login_required
def account_home(request):
    if not _participant_info_current(request.user):
        messages.add_message(request, messages.WARNING,
            'Personal information missing or out of date. <a href="update_info/">Please update!</a>',
            extra_tags='safe')
    return render(request, 'account_home.html')


def _participant_info_current(user):
    try:
        participant = user.participant
    except ObjectDoesNotExist:
        return False  # No information!
    else:
        # Information is already stored, check if it's too old
        since_last_update = timezone.now() - participant.last_updated
        return since_last_update.days < settings.MUST_UPDATE_AFTER_DAYS


@group_required('WSC')
def wsc_home(request):
    return render(request, 'wsc_home.html')


#@permission_required('ws.can_add_leader', raise_exception=True)
@group_required('WSC')
def add_leader(request):
    """ Create a Leader record for an existing Participant. """
    if request.method == "POST":
        form = forms.LeaderForm(request.POST)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS, 'Added new leader')
    else:
        # Regardless of success, empty form for quick addition of another
        form = forms.LeaderForm()
    return render(request, 'add_leader.html', {'leader_form': form})


@group_required('WSC')
def manage_leaders(request):
    LeaderFormSet = modelformset_factory(models.Leader, can_delete=True, extra=0,
                                         exclude=('participant',))
    if request.method == 'POST':
        formset = LeaderFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated leaders')
            formset = LeaderFormSet()  # Render updated forms
    else:
        formset = LeaderFormSet()
    return render(request, 'manage_leaders.html', {'formset': formset})


@group_required('WSC')
def manage_participants(request):
    ParticipantFormSet = modelformset_factory(models.Participant, can_delete=True, extra=0,
                                              fields=('attended_lectures',))
    if request.method == 'POST':
        formset = ParticipantFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated participants')
            formset = ParticipantFormSet()
    else:
        formset = ParticipantFormSet()
    return render(request, 'manage_participants.html', {'formset': formset})


@group_required('WSC')
def manage_trips(request):
    TripFormSet = modelformset_factory(models.Trip, can_delete=True, extra=0,
                                       fields=('algorithm', 'wsc_approved'))
    if request.method == 'POST':
        formset = TripFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated trips')
            formset = TripFormSet()
    else:
        formset = TripFormSet()
    return render(request, 'manage_trips.html', {'formset': formset})


class AddTrip(CreateView):
    model = models.Trip
    fields = ['leaders', 'name', 'description', 'trip_date', 'capacity',
              'leaders_willing_to_rent', 'difficulty_rating', 'prereqs',
              'algorithm']
    template_name = 'add_trip.html'
    success_url = '/accounts/view_trip/%(id)s/'

    def get_initial(self):
        """ Default with trip creator among leaders. """
        initial = super(AddTrip, self).get_initial().copy()
        initial['leaders'] = [self.request.user.participant.leader]
        return initial

    def form_valid(self, form):
        """ After is_valid(), assign creator from User. """
        creator = self.request.user.participant.leader
        trip = form.save(commit=False)
        trip.creator = creator
        # TODO: Warn if the creator isn't one of the trip leaders,
        # Prompt them to edit the trip, add themselves

        return super(AddTrip, self).form_valid(form)

    @method_decorator(group_required('WSC', 'leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super(AddTrip, self).dispatch(request, *args, **kwargs)
