"""
Views relating to an individual's membership management.

Every MITOC member is required to have a current membership and waiver. Each of
these documents expire after 12 months.
"""
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from ws import forms
from ws.decorators import participant_or_anon
from ws.waivers import initiate_waiver


class PayDuesView(FormView):
    template_name = 'profile/membership.html'
    form_class = forms.DuesForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['participant'] = self.request.participant
        return kwargs

    @method_decorator(participant_or_anon)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class SignWaiverView(FormView):
    template_name = 'profile/waiver.html'
    form_class = forms.WaiverForm
    success_url = reverse_lazy('home')

    def send_waiver(self, **kwargs):
        email, embedded_url = initiate_waiver(**kwargs)
        if not embedded_url:  # Will be sent by email
            messages.success(self.request, "Waiver sent to {}".format(email))
        return redirect(embedded_url or self.get_success_url())

    def get_guardian_form(self):
        post = self.request.POST if self.request.method == "POST" else None
        return forms.GuardianForm(post, prefix="guardian")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['prefix'] = 'releasor'
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['waiver_form'] = self.get_form(self.form_class)
        context['guardian_form'] = self.get_guardian_form()
        return context

    def form_valid(self, form):
        """ If the user submitted a name and email, use that for a waiver. """
        name, email = form.cleaned_data['name'], form.cleaned_data['email']
        return self.send_waiver(name=name, email=email, **self.guardian_info)

    @property
    def guardian_info(self):
        """ Return dictionary of guardian arguments to initiate_waiver.

        If no guardian information was submitted (via an empty or invalid form),
        this returns an empty dictionary.
        """
        guardian_form = self.get_guardian_form()
        info = {}
        if guardian_form.is_valid():
            info['guardian_name'] = guardian_form.cleaned_data['name']
            info['guardian_email'] = guardian_form.cleaned_data['email']
        return info

    def post(self, request, *args, **kwargs):
        """ Either use participant or a name+email form to submit a waiver. """
        if request.participant:
            return self.send_waiver(
                participant=request.participant, **self.guardian_info
            )

        # If there's no participant, we're just submitting an email and name directly
        f = self.get_form()
        return self.form_valid(f) if f.is_valid() else self.form_invalid(f)

    @method_decorator(participant_or_anon)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
