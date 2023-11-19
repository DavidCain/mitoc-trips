from django.http import JsonResponse
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import FormView, TemplateView

from ws import forms
from ws.decorators import participant_required
from ws.privacy import DataDump


class NeedsParticipant:
    @method_decorator(participant_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class PrivacySettingsView(NeedsParticipant, FormView):
    template_name = "privacy/settings.html"
    success_url = reverse_lazy("privacy_settings")
    form_class = forms.PrivacySettingsForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.participant
        return kwargs

    def form_valid(self, form):
        form.save()
        return super().form_valid(form)


class PrivacyView(TemplateView):
    template_name = "privacy/home.html"


class PrivacyDownloadView(TemplateView):
    template_name = "privacy/download.html"


class JsonDataDumpView(NeedsParticipant, TemplateView):
    def get(self, request, *args, **kwargs):
        data = DataDump(self.request.participant.pk)  # Re-fetch to optimize
        response = JsonResponse(data.all_data, json_dumps_params={"indent": 2})
        response["Content-Disposition"] = "attachment; filename=data_export.json"
        return response
