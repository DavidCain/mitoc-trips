from django.shortcuts import render

from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist

from ws import forms


@login_required
def update_info(request):
    """ Update stored info for participants or leaders.

    If no such information exists, update it.
    """
    # The Participant and EmergencyContact are both Person models, have
    # conflicting names. Use prefixes to keep them distinct in POST data
    par_prefix = "participant"
    e_prefix = "emergency_contact"

    # Try to identify if a Participant record already exists
    try:
        participant = request.user.participant
    except ObjectDoesNotExist:
        participant = None

    def _get_forms(request_method):
        """ Return a dictionary of forms to be passed for template rendering

        Outputs three types of forms:
            - Bound forms, if POSTed
            - Empty forms if GET, and no stored Participant data
            - Filled forms if GET, and Participant data exists

        Forms are bound to model instances for UPDATE if such instances exist.
        """
        post = request.POST if request_method == "POST" else None

        # Access other models within participant
        car = participant and participant.car
        e_info = participant and participant.emergency_info
        e_contact = e_info and e_info.emergency_contact

        # If no Participant object, fill at least with User email
        par_kwargs = {"prefix": par_prefix, "instance": participant}
        if not participant:
            par_kwargs["initial"] = {'email': request.user.email}

        form_dict = {
            'participant_form':  forms.ParticipantForm(post, **par_kwargs),
            'car_form': forms.CarForm(post, instance=car),
            'emergency_info_form':  forms.EmergencyInfoForm(post, instance=e_info),
            'emergency_contact_form':  forms.EmergencyContactForm(post, prefix=e_prefix, instance=e_contact),
        }
        return form_dict

    form_dict = _get_forms(request.method)

    if request.method == "POST":
        required_dict = form_dict.copy()

        if not 'has_car' in request.POST:
            required_dict.pop('car_form')

        if all(form.is_valid() for form in required_dict.values()):
            _save_forms(request.user, required_dict)
            return HttpResponse("Information updated", content_type="text/plain")

    return render(request, 'add_participant.html', form_dict)


def _save_forms(user, post_forms):
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
