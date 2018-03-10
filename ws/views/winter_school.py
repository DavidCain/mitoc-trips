"""
Winter School-specific views.

Some views only make sense in the context of Winter School. For example,
recording lecture attendance or toggling settings that take effect during
winter school. This module contains those views. The majority of the system
works the same during Winter School as it does during the rest of the year.
"""
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import CreateView, FormView

from ws.mixins import LectureAttendanceMixin
from ws import forms
from ws import models
from ws.utils.dates import ws_year


class LectureAttendanceView(FormView, LectureAttendanceMixin):
    """ Mark the participant as having attended lectures. """

    form_class = forms.AttendedLecturesForm

    def get(self, *args, **kwargs):
        return redirect(reverse('home'))  # (View lacks its own template)

    def form_valid(self, form):
        participant = form.cleaned_data['participant']
        if not self.can_set_attendance(participant):
            return self.form_invalid(form)

        attended, _ = models.LectureAttendance.objects.get_or_create(
            participant=participant,
            year=ws_year(),
            creator=self.request.participant
        )
        attended.save()

        # Notifications aren't shown when viewing other participants
        if participant == self.request.participant:
            messages.success(self.request, "Marked as having attended lectures!")

        return redirect(reverse('view_participant', args=(participant.id,)))


class WinterSchoolSettingsView(CreateView):
    form_class = forms.WinterSchoolSettingsForm
    template_name = 'chair/settings.html'

    def get_form_kwargs(self):
        """ Load existing settingcs. """
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = models.WinterSchoolSettings.load()
        return kwargs

    def get_success_url(self):
        messages.success(self.request, "Updated Winter School settings!")
        return reverse('ws_settings')
