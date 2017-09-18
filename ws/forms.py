from django import forms
from django.db.models.fields import TextField
from django.core.exceptions import ValidationError

from djng.forms import NgFormValidationMixin
from djng.forms import NgModelFormMixin, NgModelForm
from djng.styling.bootstrap3.forms import Bootstrap3FormMixin

from localflavor.us.us_states import US_STATES

from ws import models
from ws import widgets
from ws.utils.signups import non_trip_participants


class DjangularRequiredModelForm(NgFormValidationMixin, NgModelFormMixin, Bootstrap3FormMixin, NgModelForm):
    required_css_class = 'required'


class RequiredModelForm(forms.ModelForm):
    required_css_class = 'required'
    error_css_class = 'warning'


class DiscountForm(forms.ModelForm):
    def clean(self):
        """ Ensure the participant meets the requirements for the discount. """
        super().clean()
        participant = self.instance
        discounts = self.cleaned_data['discounts']

        if not participant.is_student:
            for discount in discounts:
                if discount.student_required:
                    err = "{} is a student-only discount".format(discount.name)
                    raise ValidationError(err)
        return self.cleaned_data

    class Meta:
        model = models.Participant
        fields = ['discounts']
        widgets = {'discounts': forms.CheckboxSelectMultiple}


class ParticipantForm(DjangularRequiredModelForm):
    name = forms.RegexField(regex=r'^.* ',
                            error_messages={"invalid": "Please use your full name"})

    class Meta:
        model = models.Participant
        fields = ['name', 'email', 'cell_phone', 'affiliation']
        widgets = {'email': forms.Select()}

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')

        # Mark any old affiliations as equivalent to blank
        # (Will properly trigger a "complete this field" warning)
        if kwargs.get('instance') and len(kwargs['instance'].affiliation) == 1:
            kwargs['instance'].affiliation = ''
        super().__init__(*args, **kwargs)

        verified_emails = user.emailaddress_set.filter(verified=True)
        choices = [email * 2 for email in verified_emails.values_list('email')]
        self.fields['email'].widget.choices = choices


class ParticipantLookupForm(forms.Form):
    """ Perform lookup of a given participant, loading on selection. """
    participant = forms.ModelChoiceField(queryset=models.Participant.objects.all())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        participant_field = self.fields['participant']
        participant_field.help_text = None  # Disable "Hold command..."
        participant_field.label = ''
        initial = kwargs.get('initial')
        if initial and initial.get('participant'):
            participant_field.empty_label = None

        participant_field.widget.attrs['onchange'] = 'this.form.submit();'


class CarForm(DjangularRequiredModelForm):
    form_name = 'car_form'

    class Meta:
        model = models.Car
        fields = ['license_plate', 'state', 'make', 'model', 'year', 'color']
        widgets = {'state': forms.Select(choices=US_STATES),
                   'year': forms.NumberInput(attrs={'min': model.year_min,
                                                    'max': model.year_max})}


class EmergencyContactForm(DjangularRequiredModelForm):

    class Meta:
        model = models.EmergencyContact
        fields = ['name', 'email', 'cell_phone', 'relationship']
        widgets = {'email': forms.TextInput()}


class EmergencyInfoForm(DjangularRequiredModelForm):

    class Meta:
        model = models.EmergencyInfo
        fields = ['allergies', 'medications', 'medical_history']
        widgets = {'medical_history': forms.Textarea(attrs={'rows': 5})}


class LeaderRecommendationForm(forms.ModelForm):
    class Meta:
        model = models.LeaderRecommendation
        exclude = []


class ApplicationLeaderForm(DjangularRequiredModelForm):
    """ Form for assigning a rating from a leader application.

    Since the participant and activity are given by the application itself,
    we need not include those an options in the form.
    """
    recommendation = forms.BooleanField(required=False, label="Is a recommendation")

    class Meta:
        model = models.LeaderRating
        fields = ['rating', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 1})}


class LeaderForm(DjangularRequiredModelForm):
    """ Allows assigning a rating to participants in any allowed activity. """
    def __init__(self, *args, **kwargs):
        allowed_activities = kwargs.pop("allowed_activities", None)
        super().__init__(*args, **kwargs)
        all_par = models.Participant.objects.all()
        self.fields['participant'].queryset = all_par
        self.fields['participant'].empty_label = 'Nobody'
        if allowed_activities is not None:
            activities = [activity for activity in self.fields['activity'].choices
                          if activity[0] in allowed_activities]
            self.fields['activity'].choices = activities

    class Meta:
        model = models.LeaderRating
        fields = ['participant', 'activity', 'rating', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 4})}


class TripInfoForm(DjangularRequiredModelForm):
    accurate = forms.BooleanField(required=True, label='I affirm that all participant and driver information is correct')

    class Meta:
        model = models.TripInfo
        fields = ['drivers', 'start_location', 'start_time', 'turnaround_time',
                  'return_time', 'worry_time', 'itinerary']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class TripForm(DjangularRequiredModelForm):

    class Meta:
        model = models.Trip
        fields = ['activity', 'name', 'leaders',
                  'allow_leader_signups',
                  'description', 'trip_date',
                  'algorithm', 'signups_open_at', 'signups_close_at',
                  'let_participants_drop', 'honor_participant_pairing',
                  'maximum_participants', 'difficulty_rating', 'level',
                  'prereqs', 'notes']
        ex_notes = (" 1. Do you have any dietary restrictions?\n"
                    " 2. What's your experience level?\n"
                    " 3. What are you most excited about?\n")
        ex_descr = '\n'.join(["We'll be heading up into the [Whites][whites] "
                              "for a ~~day~~ weekend of exploring!",
                              "",
                              "### Why?",
                              "Because it's _fun_!",
                              "",
                              "Prerequisites:",
                              " - Enthusiastic attitude",
                              " - Prior experience",
                              " - **Proper clothing**",
                              "",
                              "[whites]: https://wikipedia.org/wiki/White_Mountains_(New_Hampshire)",
                              ])

        widgets = {'leaders': widgets.LeaderSelect,
                   'description': widgets.MarkdownTextarea(ex_descr),
                   'notes': widgets.MarkdownTextarea(ex_notes),
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
        super().clean()
        activity = self.cleaned_data['activity']
        leaders = self.cleaned_data['leaders']

        lacking_privs = [par for par in leaders if not par.can_lead(activity)]

        if lacking_privs:
            names = ', '.join(leader.name for leader in lacking_privs)
            msg = "{} can't lead {} trips".format(names, activity)
            self.add_error('leaders', msg)
        return self.cleaned_data

    def clean_level(self):
        """ Remove extra whitespace from the level, strip if not WS. """
        activity = self.cleaned_data.get('activity')
        if activity != models.LeaderRating.WINTER_SCHOOL:
            return None
        return self.cleaned_data.get('level', '').strip()

    def __init__(self, *args, **kwargs):
        allowed_activities = kwargs.pop("allowed_activities", None)
        super().__init__(*args, **kwargs)
        self.fields['leaders'].queryset = models.Participant.leaders.get_queryset()
        self.fields['leaders'].help_text = None  # Disable "Hold command..."

        # We'll dynamically hide the level widget on GET if it's not a WS trip
        # On POST, we only want this field required for Winter School trips
        activity = self.data.get('activity')
        self.fields['level'].required = activity == 'winter_school' or not activity

        if allowed_activities is not None:
            activities = [vl for vl in self.fields['activity'].choices
                          if vl[0] in allowed_activities]
            self.fields['activity'].choices = activities


class SummaryTripForm(forms.ModelForm):
    """ Intended to be read-only, summarize key elements about a trip."""
    class Meta:
        model = models.Trip
        fields = ['name', 'trip_date', 'description', 'maximum_participants',
                  'algorithm', 'difficulty_rating']


class SignUpForm(DjangularRequiredModelForm):
    class Meta:
        model = models.SignUp
        fields = ['trip', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 4})}

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
        super().__init__(*args, **kwargs)
        trip = self.initial.get('trip')
        if trip and trip.notes:
            notes = self.fields['notes']
            notes.required = True
            notes.widget.attrs['placeholder'] = trip.notes
            notes.widget.attrs['rows'] = max(4, trip.notes.count('\n') + 1)


class LeaderSignUpForm(SignUpForm):
    class Meta:
        model = models.LeaderSignUp
        fields = ['trip', 'notes']


class LeaderParticipantSignUpForm(RequiredModelForm):
    """ For leaders to sign up participants. Notes aren't required. """
    top_spot = forms.BooleanField(required=False, label='Move to top spot',
                                  help_text='Move the participant above other prioritized waitlist spots (e.g. participants previously added with this form, or those who were bumped off to allow a driver on)')

    class Meta:
        model = models.SignUp
        fields = ['participant', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, trip, *args, **kwargs):
        super().__init__(*args, **kwargs)
        non_trip = non_trip_participants(trip)
        self.fields['participant'].queryset = non_trip
        self.fields['participant'].help_text = None  # Disable "Hold command..."


class LotteryInfoForm(DjangularRequiredModelForm):
    class Meta:
        model = models.LotteryInfo
        fields = ['car_status', 'number_of_passengers']
        widgets = {'car_status': forms.RadioSelect(attrs={'onclick': 'handle_driver(this);'})}


class LotteryPairForm(DjangularRequiredModelForm):
    def __init__(self, *args, **kwargs):
        participant = kwargs.pop('participant')
        exclude_self = kwargs.pop('exclude_self', False)
        super().__init__(*args, **kwargs)
        participants = models.Participant.objects.all()
        all_but_user = participants.exclude(pk=participant.pk)

        self.fields['paired_with'].queryset = all_but_user
        self.fields['paired_with'].empty_label = 'Nobody'

        # Set up arguments to be passed to Angular directive
        pair = self.fields['paired_with'].widget
        pair.attrs['msg'] = "'Nobody'"
        pair.attrs['exclude_self'] = 'true' if exclude_self else 'false'

        if self.instance.paired_with:
            pair.attrs['selected-id'] = self.instance.paired_with.pk
            pair.attrs['selected-name'] = self.instance.paired_with.name

    class Meta:
        model = models.LotteryInfo
        fields = ['paired_with']
        widgets = {'paired_with': widgets.ParticipantSelect}


class FeedbackForm(RequiredModelForm):
    class Meta:
        model = models.Feedback
        fields = ['comments', 'showed_up']


class AttendedLecturesForm(forms.Form):
    participant = forms.ModelChoiceField(queryset=models.Participant.objects.all())


class WinterSchoolSettingsForm(DjangularRequiredModelForm):
    class Meta:
        model = models.WinterSchoolSettings
        fields = ['allow_setting_attendance']


def LeaderApplicationForm(*args, **kwargs):
    """ Factory form for applying to be a leader in any activity. """
    activity = kwargs.pop('activity', 'winter_school')

    class DynamicActivityForm(DjangularRequiredModelForm):
        class Meta:
            exclude = ['year', 'participant', 'previous_rating']
            model = models.LeaderApplication.model_from_activity(activity)
            widgets = {field.name: forms.Textarea(attrs={'rows': 4})
                       for field in model._meta.fields
                       if isinstance(field, TextField)}

        def __init__(self):
            # TODO: Errors on args, where args is a single tuple of the view
            #super().__init__(*args, **kwargs)
            super().__init__(**kwargs)

    return DynamicActivityForm()
