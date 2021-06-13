"""
Winter School-specific views.

Some views only make sense in the context of Winter School. For example,
recording lecture attendance or toggling settings that take effect during
Winter School. This module contains those views. The majority of the system
works the same during Winter School as it does during the rest of the year.
"""
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, FormView

from ws import forms, models
from ws.decorators import group_required, user_info_required
from ws.mixins import LectureAttendanceMixin
from ws.utils.dates import ws_year


class LectureAttendanceView(FormView, LectureAttendanceMixin):
    """Mark the participant as having attended lectures."""

    form_class = forms.AttendedLecturesForm

    def get(self, request, *args, **kwargs):
        return redirect(reverse('home'))  # (View lacks its own template)

    def form_invalid(self, form):
        """Provide custom behavior on invalidation to compensate for lack of template.

        The default behavior from FormView is to try rendering a template with
        errors for the user. However, since the attended lectures form is
        tremendously simple (a hidden input with participant ID, and a submit
        button), there really isn't any errors we can give to the user.

        We can expect an invalid form submission when:
        1. A participant loads the attendance form (while self-submission is allowed)
        2. The Winter School chairs disable lecture sign-in
        3. The participant then tries to submit the form, but is not allowed
        """
        participant = form.cleaned_data['participant']

        # Notifications aren't shown when viewing other participants
        if participant == self.request.participant:
            messages.error(
                self.request, "Unable to record your attendance at this time."
            )

        # (note that some participants may not have access to this route!)
        return redirect(reverse('view_participant', args=(participant.pk,)))

    def form_valid(self, form):
        participant = form.cleaned_data['participant']
        if not self.can_set_attendance(participant):
            return self.form_invalid(form)

        attended, _ = models.LectureAttendance.objects.get_or_create(
            participant=participant, year=ws_year(), creator=self.request.participant
        )
        attended.save()

        # Notifications aren't shown when viewing other participants
        if participant == self.request.participant:
            messages.success(self.request, "Marked as having attended lectures!")

        return redirect(reverse('view_participant', args=(participant.pk,)))

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class WinterSchoolSettingsView(CreateView):
    form_class = forms.WinterSchoolSettingsForm
    template_name = 'chair/settings.html'

    def get_form_kwargs(self):
        """Load existing settings."""
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = models.WinterSchoolSettings.load()
        return kwargs

    def get_success_url(self):
        messages.success(self.request, "Updated Winter School settings!")
        return reverse('ws_settings')

    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
