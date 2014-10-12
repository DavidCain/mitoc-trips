from django import forms

import django_select2.widgets
from localflavor.us.us_states import US_STATES

from ws import models


class RequiredModelForm(forms.ModelForm):
    required_css_class = 'required'
    error_css_class = 'warning'


class ParticipantForm(RequiredModelForm):
    class Meta:
        model = models.Participant
        fields = ['name', 'email', 'cell_phone', 'affiliation']


class CarForm(RequiredModelForm):
    # All fields are required - 'car_row' lets JS toggle visibility of all rows
    required_css_class = 'required car_row'

    class Meta:
        model = models.Car
        fields = ['license_plate', 'state', 'make', 'model', 'year', 'color']
        widgets = {'state': forms.Select(choices=US_STATES),
                   'year': forms.NumberInput()}


class EmergencyContactForm(RequiredModelForm):
    class Meta:
        model = models.EmergencyContact
        fields = ['name', 'email', 'cell_phone', 'relationship']


class EmergencyInfoForm(RequiredModelForm):
    class Meta:
        model = models.EmergencyInfo
        fields = ['allergies', 'medications', 'medical_history']


class LeaderForm(RequiredModelForm):
    def __init__(self, *args, **kwargs):
        super(LeaderForm, self).__init__(*args, **kwargs)
        all_par = models.Participant.objects.all()
        self.fields['participant'].queryset = all_par.select_related('leader')

    class Meta:
        model = models.Leader
        fields = ['participant', 'rating']


class TripForm(RequiredModelForm):
    class Meta:
        model = models.Trip
        fields = ['leaders', 'name', 'description', 'trip_date',
                  'maximum_participants', 'difficulty_rating', 'prereqs',
                  'notes']
        widgets = {'leaders': django_select2.widgets.Select2MultipleWidget}

    def __init__(self, *args, **kwargs):
        super(TripForm, self).__init__(*args, **kwargs)
        self.fields['leaders'].help_text = None  # Disable "Hold command..."


class SummaryTripForm(forms.ModelForm):
    """ Intended to be read-only, cover key elements. Seen on view_trips. """
    class Meta:
        model = models.Trip
        fields = ['name', 'trip_date', 'description', 'maximum_participants', 'algorithm',
                'difficulty_rating']


class SignUpForm(RequiredModelForm):
    class Meta:
        model = models.SignUp
        fields = ['trip', 'notes']


class LotteryInfoForm(RequiredModelForm):
    class Meta:
        model = models.LotteryInfo
        fields = ['own_a_car', 'willing_to_rent', 'number_of_passengers']


class FeedbackForm(RequiredModelForm):
    class Meta:
        model = models.Feedback
        fields = ['comments', 'showed_up', 'prefer_anonymous']
