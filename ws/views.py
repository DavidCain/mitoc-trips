from django.shortcuts import render

from ws import forms

from django.http import HttpResponse
from django.contrib.auth.decorators import login_required


@login_required
def add_participant(request):
    """ Create a new Participant record, and related records. """
    # The Participant and EmergencyContact are both Person models, have
    # conflicting names. Use prefixes to keep them distinct in POST data
    par_prefix = "participant"
    e_prefix = "emergency_contact"

    if request.method == "POST":
        post = request.POST

        # Build forms from POST data
        participant_form = forms.ParticipantForm(post, prefix=par_prefix)
        car_form = forms.CarForm(post)
        e_info_form = forms.EmergencyInfoForm(post)
        e_contact_form = forms.EmergencyContactForm(post, prefix=e_prefix)

        # If all forms valid, save to database (else, bound forms go back)
        required_forms = [participant_form, e_info_form, e_contact_form]
        if 'has_car' in post:
            required_forms.append(car_form)
        if all(form.is_valid() for form in required_forms):
            e_contact = e_contact_form.save()
            e_info = e_info_form.save(commit=False)
            e_info.emergency_contact = e_contact
            e_info = e_info_form.save()
            car = car_form.save()

            participant = participant_form.save(commit=False)
            participant.car = car
            participant.emergency_info = e_info
            participant.save()
            return HttpResponse("Participant added!", content_type="text/plain")

    else:
        participant_form = forms.ParticipantForm(prefix=par_prefix)
        car_form = forms.CarForm()
        e_info_form = forms.EmergencyInfoForm()
        e_contact_form = forms.EmergencyContactForm(prefix=e_prefix)

    # Returns unbound (empty) forms, or bound, erroneous forms
    form_dict = {'participant_form': participant_form,
                 'car_form': car_form,
                 'emergency_info_form': e_info_form,
                 'emergency_contact_form': e_contact_form,
                 }
    return render(request, 'add_participant.html', form_dict)
