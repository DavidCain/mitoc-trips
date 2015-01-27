from django import forms

import django_select2.widgets
from django_select2.fields import ModelSelect2MultipleField
from localflavor.us.us_states import US_STATES

from ws import models
from ws import signup_utils


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
                   'year': forms.NumberInput(attrs={'min': model.year_min,
                                                    'max': model.year_max})}


class EmergencyContactForm(RequiredModelForm):
    class Meta:
        model = models.EmergencyContact
        fields = ['name', 'email', 'cell_phone', 'relationship']


class EmergencyInfoForm(RequiredModelForm):
    class Meta:
        model = models.EmergencyInfo
        fields = ['allergies', 'medications', 'medical_history']
        widgets = {'medical_history': forms.Textarea(attrs={'rows': 5})}


class LeaderForm(RequiredModelForm):
    def __init__(self, *args, **kwargs):
        super(LeaderForm, self).__init__(*args, **kwargs)
        all_par = models.Participant.objects.all()
        self.fields['participant'].queryset = all_par.select_related('leader')
        self.fields['participant'].empty_label = 'Nobody'

    class Meta:
        model = models.Leader
        fields = ['participant', 'rating', 'notes']
        widgets = {'participant': django_select2.widgets.Select2Widget,
                   'notes': forms.Textarea(attrs={'rows': 4})}


class TripInfoForm(RequiredModelForm):
    accurate = forms.BooleanField(required=True, label='I affirm that all participant and driver information is correct')

    class Meta:
        model = models.TripInfo
        fields = ['drivers', 'start_location', 'start_time', 'turnaround_time',
                  'return_time', 'worry_time', 'itinerary']
        widgets = {'drivers': django_select2.widgets.Select2MultipleWidget}

    def __init__(self, *args, **kwargs):
        super(TripInfoForm, self).__init__(*args, **kwargs)
        self.fields['drivers'].help_text = self.fields['drivers'].help_text


class TripForm(RequiredModelForm):
    class Meta:
        model = models.Trip
        fields = ['name', 'leaders', 'description', 'trip_date',
                  'maximum_participants', 'difficulty_rating', 'prereqs',
                  'notes']
        widgets = {'leaders': django_select2.widgets.Select2MultipleWidget,
                   'notes': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super(TripForm, self).__init__(*args, **kwargs)
        self.fields['leaders'].help_text = None  # Disable "Hold command..."


class SummaryTripForm(forms.ModelForm):
    """ Intended to be read-only, cover key elements. Seen on view_trips. """
    class Meta:
        model = models.Trip
        fields = ['name', 'trip_date', 'description', 'maximum_participants',
                  'algorithm', 'difficulty_rating']


class SignUpForm(RequiredModelForm):
    class Meta:
        model = models.SignUp
        fields = ['trip', 'notes']

    def __init__(self, *args, **kwargs):
        """ Set notes to required if trip notes are present.

        Trips should always be given via initial. We can check if the trip
        has a notes field this way.
        """
        super(SignUpForm, self).__init__(*args, **kwargs)
        trip = self.initial.get('trip')
        if trip and trip.notes:
            self.fields['notes'].required = True


class LeaderSignUpForm(RequiredModelForm):
    top_spot = forms.BooleanField(required=False, label='Move to top spot',
                                  help_text='Move the participant above other prioritized waitlist spots (e.g. participants previously added with this form, or those who were bumped off to allow a driver on)')

    class Meta:
        model = models.SignUp
        fields = ['participant', 'notes']
        widgets = {'participant': django_select2.widgets.Select2Widget,
                   'notes': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, trip, *args, **kwargs):
        super(LeaderSignUpForm, self).__init__(*args, **kwargs)
        self.fields['participant'].queryset = signup_utils.non_trip_participants(trip)
        self.fields['participant'].help_text = None  # Disable "Hold command..."


class LotteryInfoForm(forms.ModelForm):
    class Meta:
        model = models.LotteryInfo
        fields = ['car_status', 'number_of_passengers']
        widgets = {'car_status': forms.RadioSelect(attrs={'onclick': 'handle_driver(this);'})}


class LotteryPairForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super(LotteryPairForm, self).__init__(*args, **kwargs)
        participants = models.Participant.objects.all()
        all_but_user = participants.exclude(pk=user.participant.pk)
        self.fields['paired_with'].queryset = all_but_user.select_related('leader')
        self.fields['paired_with'].empty_label = 'Nobody'

    class Meta:
        model = models.LotteryInfo
        fields = ['paired_with']
        widgets = {'paired_with': django_select2.widgets.Select2Widget}


class FeedbackForm(RequiredModelForm):
    class Meta:
        model = models.Feedback
        fields = ['comments', 'showed_up']


class FlakeForm(forms.Form):
    flakers = ModelSelect2MultipleField(required=False)

    def __init__(self, trip, *args, **kwargs):
        super(FlakeForm, self).__init__(*args, **kwargs)
        self.fields['flakers'].queryset = signup_utils.non_trip_participants(trip)
        self.fields['flakers'].help_text = None  # Disable "Hold command..."


class AttendedLecturesForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput())


class LeaderApplicationForm(RequiredModelForm):
    class Meta:
        exclude = ['participant']
        model = models.LeaderApplication
