from django import forms
from django.core.exceptions import ValidationError

from djangular.forms import NgFormValidationMixin, NgForm
from djangular.forms import NgModelFormMixin, NgModelForm
from djangular.styling.bootstrap3.forms import Bootstrap3Form, Bootstrap3FormMixin

from localflavor.us.us_states import US_STATES

from ws import models
from ws import signup_utils
from ws import perm_utils
from ws import widgets


class DjangularRequiredModelForm(NgFormValidationMixin, NgModelFormMixin, Bootstrap3FormMixin, NgModelForm):
    required_css_class = 'required'


class RequiredModelForm(forms.ModelForm):
    required_css_class = 'required'
    error_css_class = 'warning'


class ParticipantForm(DjangularRequiredModelForm):
    required_css_class = 'required'
    class Meta:
        model = models.Participant
        fields = ['name', 'email', 'cell_phone', 'affiliation']


class ParticipantLookupForm(forms.Form):
    """ Perform lookup of a given participant, loading on selection. """
    participant = forms.ModelChoiceField(queryset=models.Participant.objects.all())

    def __init__(self, *args, **kwargs):
        super(ParticipantLookupForm, self).__init__(*args, **kwargs)
        participant_field = self.fields['participant']
        participant_field.help_text = None  # Disable "Hold command..."
        participant_field.label = ''
        initial = kwargs.get('initial')
        if initial and initial.get('participant'):
            participant_field.empty_label = None

        participant_field.widget.attrs['onchange'] = 'this.form.submit();'


class CarForm(DjangularRequiredModelForm):
    required_css_class = 'required'
    form_name = 'car_form'

    class Meta:
        model = models.Car
        fields = ['license_plate', 'state', 'make', 'model', 'year', 'color']
        widgets = {'state': forms.Select(choices=US_STATES),
                   'year': forms.NumberInput(attrs={'min': model.year_min,
                                                    'max': model.year_max})}


class EmergencyContactForm(DjangularRequiredModelForm):
    required_css_class = 'required'
    class Meta:
        model = models.EmergencyContact
        fields = ['contact_name', 'contact_email', 'contact_cell_phone', 'relationship']


class EmergencyInfoForm(DjangularRequiredModelForm):
    required_css_class = 'required'
    class Meta:
        model = models.EmergencyInfo
        fields = ['allergies', 'medications', 'medical_history']
        widgets = {'medical_history': forms.Textarea(attrs={'rows': 5})}


class LeaderForm(DjangularRequiredModelForm):
    def __init__(self, *args, **kwargs):
        allowed_activities = kwargs.pop("allowed_activities", None)
        super(LeaderForm, self).__init__(*args, **kwargs)
        all_par = models.Participant.objects.all()
        self.fields['participant'].queryset = all_par
        self.fields['participant'].empty_label = 'Nobody'
        if allowed_activities is not None:
            activities = filter(lambda (val, label): val in allowed_activities,
                                self.fields['activity'].choices)
            self.fields['activity'].choices = activities

    class Meta:
        model = models.LeaderRating
        fields = ['participant', 'activity', 'rating', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 4})}


class TripInfoForm(DjangularRequiredModelForm):
    required_css_class = 'required'
    accurate = forms.BooleanField(required=True, label='I affirm that all participant and driver information is correct')

    class Meta:
        model = models.TripInfo
        fields = ['drivers', 'start_location', 'start_time', 'turnaround_time',
                  'return_time', 'worry_time', 'itinerary']

    def __init__(self, *args, **kwargs):
        super(TripInfoForm, self).__init__(*args, **kwargs)
        self.fields['drivers'].help_text = self.fields['drivers'].help_text


class TripForm(DjangularRequiredModelForm):
    required_css_class = 'required'

    class Meta:
        model = models.Trip
        fields = ['activity', 'name', 'leaders', 'description', 'trip_date',
                  'maximum_participants', 'difficulty_rating', 'level',
                  'prereqs', 'notes']
        widgets = {#'leaders': widgets.LeaderSelect,
                   'description': forms.Textarea(attrs={'rows': 4}),
                   'notes': forms.Textarea(attrs={'rows': 4}),
                   'trip_date': widgets.BootstrapDateInput()}

    def clean_maximum_participants(self):
        trip = self.instance
        new_max = self.cleaned_data['maximum_participants']
        accepted_signups = trip.signup_set.filter(on_trip=True).count()
        if self.instance and accepted_signups > new_max:
            msg = ("Can't shrink trip past number of signed-up participants. "
                   "To remove participants, admin this trip instead.")
            raise ValidationError(msg)
        return new_max

    def clean(self):
        """ Ensure that all leaders can lead the trip.

        We do this in the form instead of the model, because we don't
        want ValidationErrors when trying to modify old trips where a
        leader rating may have lapsed.
        """
        super(TripForm, self).clean()
        lacking_privs = []
        activity = self.cleaned_data['activity']
        for leader in self.cleaned_data['leaders']:
            if not leader.leaderrating_set.filter(activity=activity):
                lacking_privs.append(leader)
        if lacking_privs:
            names = ', '.join(leader.name for leader in lacking_privs)
            msg = "{} can't lead {} trips".format(names, activity)
            self.add_error('leaders', msg)

    def __init__(self, *args, **kwargs):
        allowed_activities = kwargs.pop("allowed_activities", None)
        super(TripForm, self).__init__(*args, **kwargs)
        self.fields['leaders'].queryset = models.Participant.leaders.get_queryset()
        self.fields['leaders'].help_text = None  # Disable "Hold command..."
        if allowed_activities is not None:
            activities = filter(lambda (val, label): val in allowed_activities,
                                self.fields['activity'].choices)
            self.fields['activity'].choices = activities


class SummaryTripForm(forms.ModelForm):
    """ Intended to be read-only, cover key elements. Seen on view_trips. """
    class Meta:
        model = models.Trip
        fields = ['name', 'trip_date', 'description', 'maximum_participants',
                  'algorithm', 'difficulty_rating']


class SignUpForm(DjangularRequiredModelForm):
    class Meta:
        model = models.SignUp
        fields = ['trip', 'notes']

    def clean_notes(self):
        trip = self.cleaned_data['trip']
        signup_notes = self.cleaned_data['notes'].strip()
        if trip.notes and not signup_notes:
            raise ValidationError("Please complete notes to sign up!")
        return signup_notes

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
    """ For leaders to sign up participants. Notes aren't required. """
    top_spot = forms.BooleanField(required=False, label='Move to top spot',
                                  help_text='Move the participant above other prioritized waitlist spots (e.g. participants previously added with this form, or those who were bumped off to allow a driver on)')

    class Meta:
        model = models.SignUp
        fields = ['participant', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, trip, *args, **kwargs):
        super(LeaderSignUpForm, self).__init__(*args, **kwargs)
        non_trip = signup_utils.non_trip_participants(trip)
        self.fields['participant'].queryset = non_trip
        self.fields['participant'].help_text = None  # Disable "Hold command..."


class LotteryInfoForm(DjangularRequiredModelForm):
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
        self.fields['paired_with'].queryset = all_but_user
        self.fields['paired_with'].empty_label = 'Nobody'

    class Meta:
        model = models.LotteryInfo
        fields = ['paired_with']


class FeedbackForm(RequiredModelForm):
    class Meta:
        model = models.Feedback
        fields = ['comments', 'showed_up']


class FlakeForm(forms.Form):
    flakers = forms.ModelMultipleChoiceField(required=False, queryset=None)

    def __init__(self, trip, *args, **kwargs):
        super(FlakeForm, self).__init__(*args, **kwargs)
        self.fields['flakers'].queryset = signup_utils.non_trip_participants(trip)
        self.fields['flakers'].help_text = None  # Disable "Hold command..."


class AttendedLecturesForm(NgFormValidationMixin, Bootstrap3Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput())


class LeaderApplicationForm(DjangularRequiredModelForm):
    class Meta:
        exclude = ['participant']
        model = models.LeaderApplication
