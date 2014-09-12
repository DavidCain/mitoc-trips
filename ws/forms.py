from django import forms

from ws import models


class ParticipantForm(forms.ModelForm):
    class Meta:
        model = models.Participant
        fields = ['name', 'email', 'cell_phone', 'affiliation']


class CarForm(forms.ModelForm):
    class Meta:
        model = models.Car
        fields = ['license_plate', 'state', 'make', 'model', 'year']


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
        fields = ['leaders', 'name', 'description', 'trip_date', 'capacity',
                  'leaders_willing_to_rent', 'difficulty_rating', 'prereqs',
                  'algorithm']
