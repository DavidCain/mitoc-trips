from typing import List, Tuple, Union

from django import forms
from django.core.exceptions import ValidationError
from django.db.models.fields import TextField
from djng.forms.fields import BooleanField, CharField, ChoiceField, EmailField
from localflavor.us.us_states import US_STATES
from mitoc_const import affiliations

from ws import enums, models, widgets
from ws.membership import MERCHANT_ID, PAYMENT_TYPE
from ws.utils.signups import non_trip_participants


class RequiredModelForm(forms.ModelForm):
    required_css_class = 'required'
    error_css_class = 'warning'


class DiscountForm(forms.ModelForm):
    def clean_discounts(self):
        """Ensure the participant meets the requirements for each discount."""
        participant = self.instance
        discounts = self.cleaned_data['discounts']

        if not participant.is_student:
            for discount in discounts:
                if discount.student_required:
                    raise ValidationError(f"{discount.name} is a student-only discount")
                if not discount.ga_key:
                    # The UI should prevent "enrolling" in these read-only discounts, but check anyway.
                    raise ValidationError(
                        f"{discount.name} does not support sharing your information automatically. "
                        "See discount terms for instructions."
                    )

        return discounts

    class Meta:
        model = models.Participant
        fields = ['discounts']
        widgets = {'discounts': forms.CheckboxSelectMultiple}


class ParticipantForm(forms.ModelForm):
    class Meta:
        model = models.Participant
        fields = ['name', 'email', 'cell_phone', 'affiliation']
        widgets = {
            'name': forms.TextInput(
                attrs={'title': 'Full name', 'pattern': r'^.* .*$'}
            ),
            'email': forms.Select(),
            'cell_phone': widgets.PhoneInput,
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')

        # Mark any old affiliations as equivalent to blank
        # (Will properly trigger a "complete this field" warning)
        if kwargs.get('instance') and len(kwargs['instance'].affiliation) == 1:
            kwargs['instance'].affiliation = ''

        super().__init__(*args, **kwargs)

        self.verified_emails = user.emailaddress_set.filter(verified=True).values_list(
            'email', flat=True
        )
        self.fields['email'].widget.choices = [
            (email, email) for email in self.verified_emails
        ]

        self.fields['affiliation'].widget.attrs['data-ng-model'] = 'affiliation'

    def clean_affiliation(self):
        """Require a valid MIT email address for MIT student affiliation."""
        mit_student_codes = {
            affiliations.MIT_UNDERGRAD.CODE,
            affiliations.MIT_GRAD_STUDENT.CODE,
        }
        affiliation = self.cleaned_data['affiliation']
        if affiliation not in mit_student_codes:
            return affiliation  # Nothing extra needs to be done!
        if not any(email.lower().endswith('mit.edu') for email in self.verified_emails):
            raise ValidationError(
                "MIT email address required for student affiliation!",
                code="lacks_mit_email",
            )
        return affiliation


class ParticipantLookupForm(forms.Form):
    """Perform lookup of a given participant, loading on selection."""

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


class CarForm(forms.ModelForm):
    form_name = 'car_form'

    def clean_license_plate(self):
        return self.cleaned_data['license_plate'].upper()

    class Meta:
        model = models.Car
        fields = ['license_plate', 'state', 'make', 'model', 'year', 'color']
        widgets = {
            'state': forms.Select(choices=US_STATES),
            'year': forms.NumberInput(
                attrs={'min': model.year_min, 'max': model.year_max}
            ),
        }


class EmergencyContactForm(forms.ModelForm):
    class Meta:
        model = models.EmergencyContact
        fields = ['name', 'email', 'cell_phone', 'relationship']
        widgets = {
            'name': forms.TextInput(
                attrs={'title': 'Full name', 'pattern': r'^.* .*$'}
            ),
            'email': forms.TextInput(),
            'cell_phone': widgets.PhoneInput,
        }


class EmergencyInfoForm(forms.ModelForm):
    class Meta:
        model = models.EmergencyInfo
        fields = ['allergies', 'medications', 'medical_history']
        widgets = {'medical_history': forms.Textarea(attrs={'rows': 5})}


class LeaderRecommendationForm(forms.ModelForm):
    class Meta:
        model = models.LeaderRecommendation
        exclude: List[str] = []


class ApplicationLeaderForm(forms.ModelForm):
    """Form for assigning a rating from a leader application.

    Since the participant and activity are given by the application itself,
    we need not include those an options in the form.
    """

    is_recommendation = BooleanField(required=False, label="Is a recommendation")

    class Meta:
        model = models.LeaderRating
        fields = ['rating', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 1})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # We bind the field to an ng-model to enable conditional content on submit button
        self.fields['is_recommendation'].widget.attrs['data-ng-model'] = 'is_rec'


class LeaderForm(forms.ModelForm):
    """Allows assigning a rating to participants in any allowed activity."""

    def __init__(self, *args, **kwargs):
        allowed_activities = kwargs.pop("allowed_activities", None)
        hide_activity = kwargs.pop('hide_activity', False)

        super().__init__(*args, **kwargs)

        all_par = models.Participant.objects.all()
        self.fields['participant'].queryset = all_par
        self.fields['participant'].empty_label = 'Nobody'

        if allowed_activities is not None:
            allowed_activity_values = {
                activity_enum.value for activity_enum in allowed_activities
            }
            activities = [
                (val, label)
                for (val, label) in self.fields['activity'].choices
                if val in allowed_activity_values
            ]
            self.fields['activity'].choices = activities
            if activities:
                self.fields['activity'].initial = activities[0]
        if hide_activity:
            self.fields['activity'].widget = forms.HiddenInput()

        # Give each field an ng-model so that the `leaderRating` controller can manage the form.
        # (We query ratings for a given participant + activity, then set rating & notes with the result)
        for field_name in ['participant', 'activity', 'rating', 'notes']:
            self.fields[field_name].widget.attrs['data-ng-model'] = field_name

    class Meta:
        model = models.LeaderRating
        fields = ['participant', 'activity', 'rating', 'notes']
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
            'participant': widgets.ParticipantSelect,
        }


class TripInfoForm(forms.ModelForm):
    accurate = forms.BooleanField(
        required=True,
        label='I affirm that all participant and driver information is correct',
    )

    class Meta:
        model = models.TripInfo
        fields = [
            'drivers',
            'start_location',
            'start_time',
            'turnaround_time',
            'return_time',
            'worry_time',
            'itinerary',
        ]


class TripForm(forms.ModelForm):
    class Meta:
        model = models.Trip
        fields = [
            'program',
            'trip_type',
            'name',
            'leaders',
            'wimp',
            'allow_leader_signups',
            'description',
            'trip_date',
            'algorithm',
            'signups_open_at',
            'signups_close_at',
            'let_participants_drop',
            'honor_participant_pairing',
            'membership_required',
            'maximum_participants',
            'difficulty_rating',
            'level',
            'prereqs',
            'notes',
        ]
        ex_notes = (
            " 1. Do you have any dietary restrictions?\n"
            " 2. What's your experience level?\n"
            " 3. What are you most excited about?\n"
        )
        ex_descr = '\n'.join(
            [
                "We'll be heading up into the [Whites][whites] "
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
            ]
        )

        widgets = {
            'leaders': widgets.LeaderSelect,
            'wimp': widgets.ParticipantSelect,
            'description': widgets.MarkdownTextarea(ex_descr),
            'notes': widgets.MarkdownTextarea(ex_notes),
            'trip_date': widgets.BootstrapDateInput(),
        }

    def clean_membership_required(self):
        """Ensure that all WS trips require membership."""
        if self.cleaned_data.get('program') == enums.Program.WINTER_SCHOOL.value:
            return True
        return self.cleaned_data['membership_required']

    def clean_maximum_participants(self):
        trip = self.instance
        new_max = self.cleaned_data['maximum_participants']
        accepted_signups = trip.signup_set.filter(on_trip=True).count()
        if self.instance and accepted_signups > new_max:
            raise ValidationError(
                "Can't shrink trip past number of signed-up participants. "
                "To remove participants, admin this trip instead."
            )
        return new_max

    def clean(self):
        """Ensure that all leaders can lead the trip."""
        super().clean()

        if 'program' not in self.cleaned_data or 'leaders' not in self.cleaned_data:
            return self.cleaned_data
        leaders = self.cleaned_data['leaders']
        program_enum = enums.Program(self.cleaned_data['program'])

        # To allow editing old trips with lapsed leaders, only check new additions
        trip = self.instance
        if trip.pk:
            leaders = leaders.exclude(pk__in=trip.leaders.all())

        lacking_privs = [par for par in leaders if not par.can_lead(program_enum)]

        if lacking_privs:
            names = ', '.join(leader.name for leader in lacking_privs)
            self.add_error('leaders', f"{names} can't lead {program_enum.label} trips")
        return self.cleaned_data

    def clean_level(self):
        """Remove extra whitespace from the level, strip if not WS."""
        program = self.cleaned_data.get('program')
        program_enum = enums.Program(program) if program else None
        if program_enum and not program_enum.winter_rules_apply():
            return None
        return self.cleaned_data.get('level', '').strip()

    def _init_wimp(self):
        """Configure the WIMP widget, load saved participant if applicable."""
        wimp = self.fields['wimp'].widget
        wimp.attrs['msg'] = "'Nobody'"
        wimp.attrs['exclude_self'] = 'true'

        if self.instance.wimp:
            wimp.attrs['selected-id'] = self.instance.wimp.pk
            wimp.attrs['selected-name'] = self.instance.wimp.name

    def _allowed_program_choices(self, allowed_program_enums):
        # If editing an existing trip, the old program can persist.
        if self.instance and self.instance.program_enum not in allowed_program_enums:
            allowed_program_enums = [self.instance.program_enum, *allowed_program_enums]

        for category, choices in enums.Program.choices():
            assert isinstance(category, str) and isinstance(choices, list)
            valid_choices = [
                (value, label)
                for (value, label) in choices
                if enums.Program(value) in allowed_program_enums
            ]
            if valid_choices:
                yield (category, valid_choices)

    def __init__(self, *args, **kwargs):
        allowed_programs = kwargs.pop("allowed_programs", None)
        super().__init__(*args, **kwargs)
        # Use the participant queryset to cover an edge case:
        # editing an old trip where one of the leaders is no longer a leader!
        self.fields['leaders'].queryset = models.Participant.objects.get_queryset()
        self.fields['leaders'].help_text = None  # Disable "Hold command..."

        # We'll dynamically hide the level widget on GET if it's not a winter trip
        # On POST, we only want this field required for winter trips
        program = self.data.get('program')
        program_enum = enums.Program(program) if program else None
        self.fields['level'].required = (
            program_enum and program_enum.winter_rules_apply()
        )

        if allowed_programs is not None:
            self.fields['program'].choices = list(
                self._allowed_program_choices(allowed_programs)
            )

        self._init_wimp()

        # `trip_date` is particularly important to assign a model to!
        for field_name in ('program', 'algorithm', 'leaders', 'trip_date'):
            self.fields[field_name].widget.attrs['data-ng-model'] = field_name


class SignUpForm(forms.ModelForm):
    class Meta:
        model = models.SignUp
        fields = ['trip', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 4})}

    def clean_notes(self):
        signup_notes = self.cleaned_data['notes'].strip()
        if 'trip' not in self.cleaned_data:
            return signup_notes

        trip = self.cleaned_data['trip']
        if trip.notes and not signup_notes:
            raise ValidationError("Please complete notes to sign up!")
        return signup_notes

    def __init__(self, *args, **kwargs):
        """Set notes to required if trip notes are present.

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
    """For leaders to sign up participants. Notes aren't required."""

    top_spot = BooleanField(
        required=False,
        label='Move to top spot',
        help_text=(
            'Move the participant above other prioritized waitlist '
            'spots (e.g. participants previously added with this form, '
            'or those who were bumped off to allow a driver on)'
        ),
    )

    class Meta:
        model = models.SignUp
        fields = ['participant', 'notes']
        widgets = {'notes': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, trip, *args, **kwargs):
        super().__init__(*args, **kwargs)
        non_trip = non_trip_participants(trip)
        self.fields['participant'].queryset = non_trip
        self.fields['participant'].help_text = None  # Disable "Hold command..."


class LotteryInfoForm(forms.ModelForm):
    class Meta:
        model = models.LotteryInfo
        fields = ['car_status', 'number_of_passengers']
        widgets = {
            'number_of_passengers': forms.NumberInput(
                attrs={'min': 0, 'max': 13}  # hard-coded, but matches model
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name in ['car_status', 'number_of_passengers']:
            self.fields[field_name].widget.attrs['data-ng-model'] = field_name


class LotteryPairForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        participant = kwargs.pop('participant')

        super().__init__(*args, **kwargs)

        paired_with = self.fields['paired_with']
        paired_with.queryset = models.Participant.objects.exclude(pk=participant.pk)
        paired_with.empty_label = 'Nobody'

        # Set up arguments to be passed to Angular directive
        widget = paired_with.widget
        widget.attrs['data-ng-model'] = 'paired_with'
        widget.attrs['data-msg'] = "'Nobody'"
        widget.attrs['data-exclude_self'] = 'true'

        if self.instance.paired_with:
            widget.attrs['data-selected-id'] = self.instance.paired_with.pk
            widget.attrs['data-selected-name'] = self.instance.paired_with.name

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


class WinterSchoolSettingsForm(forms.ModelForm):
    class Meta:
        model = models.WinterSchoolSettings
        fields = ['allow_setting_attendance', 'accept_applications']


# TODO: This should be a class, not a method.
def LeaderApplicationForm(*args, **kwargs):
    """Factory form for applying to be a leader in any activity."""
    activity = kwargs.pop('activity')

    class DynamicActivityForm(forms.ModelForm):
        class Meta:
            exclude = ['archived', 'year', 'participant', 'previous_rating']
            model = models.LeaderApplication.model_from_activity(activity)
            widgets = {
                field.name: forms.Textarea(attrs={'rows': 4})
                for field in model._meta.fields  # pylint: disable=protected-access
                if isinstance(field, TextField)
            }

        def clean(self):
            cleaned_data = super().clean()
            if not models.LeaderApplication.accepting_applications(activity):
                raise ValidationError("Not currently accepting applications!")
            return cleaned_data

        def __init__(self, *args, **kwargs):
            # TODO: Errors on args, where args is a single tuple of the view
            # super().__init__(*args, **kwargs)
            super().__init__(**kwargs)

            # For fields which are conditionally shown/hidden, set the required attr
            # Critically, we must *not* actually make the *field* required.
            # The idea is to just tell the browser that the input is required.
            # (we don't want to fail a form submission for somebody who doesn't want mentorship)
            #
            # We should *perhaps* reconsider this hack to make the application work without JS
            # (we use JavaScript to conditionally hide this div)
            for conditional_field in ('mentee_activities', 'mentor_activities'):
                if conditional_field in self.fields:
                    self.fields[conditional_field].widget.attrs['required'] = True

    return DynamicActivityForm(*args, **kwargs)


def amount_choices(value_is_amount=False):
    """Yield all affiliation choices with the price in the label.

    If `value_is_amount` is True, we'll replace the two-letter affiliation
    with the price as the choice's value.
    """

    def include_amount_in_label(
        affiliation_code: str, label: str
    ) -> Tuple[Union[int, str], str]:
        amount = models.Participant.affiliation_to_membership_price(affiliation_code)
        annotated_label = f"{label} (${amount})"

        if value_is_amount:
            return (amount, annotated_label)
        return (affiliation_code, annotated_label)

    for label, option in models.Participant.AFFILIATION_CHOICES:
        if isinstance(option, list):
            # The options are a collection of affiliation codes
            yield label, [include_amount_in_label(*choice) for choice in option]
        else:
            # It's a top-level choice - the label & option are actually switched
            yield include_amount_in_label(label, option)


class DuesForm(forms.Form):
    """Provide a form that's meant to submit its data to CyberSource.

    Specifically, each of these named fields is what's expected for MIT's
    payment system to process a credit card payment and link it to user-supplied
    metadata. For example, `merchantDefinedData3` is the member's email address.

    The expected URL is https://shopmitprd.mit.edu/controller/index.php
    """

    merchant_id = CharField(widget=forms.HiddenInput(), initial=MERCHANT_ID)
    description = CharField(widget=forms.HiddenInput(), initial='membership fees.')

    merchantDefinedData1 = CharField(widget=forms.HiddenInput(), initial=PAYMENT_TYPE)
    merchantDefinedData2 = ChoiceField(
        required=True, label='Affiliation', choices=list(amount_choices())
    )
    merchantDefinedData3 = EmailField(required=True, label='Email')

    # For Participant-less users with JS enabled, this will be hidden & silently
    # set by an Angular directive that updates the amount based on the affiliation.
    # For users _without_ JavaScript, it will display as a Select widget.
    amount = ChoiceField(
        label='Please confirm membership level',
        required=True,
        help_text="(We're showing this because you have scripts disabled)",
        choices=list(amount_choices(value_is_amount=True)),
    )

    def __init__(self, *args, **kwargs):
        participant = kwargs.pop('participant')

        super().__init__(*args, **kwargs)
        email = self.fields['merchantDefinedData3']

        # We conditionally show messages about MIT affiliation, disable submission, etc.
        self.fields['merchantDefinedData2'].widget.attrs['ng-model'] = 'affiliation'
        self.fields['merchantDefinedData3'].widget.attrs['ng-model'] = 'email'

        if participant:
            email.initial = participant.email
            self.fields['merchantDefinedData2'].initial = participant.affiliation
            self.fields['amount'].initial = participant.annual_dues
        else:
            email.widget.attrs['placeholder'] = 'tim@mit.edu'
            # Without this, the default choice is 'Undergraduate student'.
            # This heading doesn't render as a choice, but it behaves like one.
            self.fields['amount'].initial = ''


class WaiverForm(forms.Form):
    name = forms.CharField(required=True)
    email = forms.EmailField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs['placeholder'] = 'Tim Beaver'
        self.fields['email'].widget.attrs['placeholder'] = 'tim@mit.edu'


class GuardianForm(forms.Form):
    name = forms.CharField(required=True, label='Parent or Guardian Name')
    email = forms.EmailField(required=True, label='Parent or Guardian Email')


class PrivacySettingsForm(forms.ModelForm):
    class Meta:
        model = models.Participant
        fields = ['gravatar_opt_out']
