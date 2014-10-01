from django import forms

from ws import models


class ParticipantForm(forms.ModelForm):
    class Meta:
        model = models.Participant
        fields = ['name', 'email', 'cell_phone', 'affiliation']


class CarForm(forms.ModelForm):
    class Meta:
        model = models.Car
        fields = ['license_plate', 'state', 'make', 'model', 'year', 'color']


class EmergencyContactForm(forms.ModelForm):
    class Meta:
        model = models.EmergencyContact
        fields = ['name', 'email', 'cell_phone', 'relationship']


class EmergencyInfoForm(forms.ModelForm):
    class Meta:
        model = models.EmergencyInfo
        fields = ['allergies', 'medications', 'medical_history']


class LeaderForm(forms.ModelForm):
    class Meta:
        model = models.Leader
        fields = ['participant', 'rating']


class TripForm(forms.ModelForm):
    class Meta:
        model = models.Trip
        fields = ['leaders', 'name', 'description', 'trip_date',
                  'maximum_participants', 'leaders_willing_to_rent',
                  'difficulty_rating', 'prereqs', 'algorithm',
                  'signups_open_at', 'signups_close_at', 'notes']


class SummaryTripForm(forms.ModelForm):
    """ Intended to be read-only, cover key elements. Seen on view_trips. """
    class Meta:
        model = models.Trip
        fields = ['name', 'trip_date', 'description', 'maximum_participants', 'algorithm',
                'difficulty_rating']


class SignUpForm(forms.ModelForm):
    class Meta:
        model = models.SignUp
        fields = ['trip', 'notes']


class LotteryInfoForm(forms.ModelForm):
    class Meta:
        model = models.LotteryInfo
        fields = ['own_a_car', 'willing_to_rent', 'number_of_passengers']


class FeedbackForm(forms.ModelForm):
    class Meta:
        model = models.Feedback
        fields = ['comments', 'showed_up', 'prefer_anonymous']
