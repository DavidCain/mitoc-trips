from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import modelformset_factory
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.generic import View

from ws import forms
from ws import models


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


@login_required
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


@login_required
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
