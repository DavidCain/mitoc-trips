"""
Views relating to an individual's membership management.

Every MITOC member is required to have a current membership and waiver. Each of
these documents expire after 12 months.
"""
from typing import Optional

from django.contrib import messages
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import FormView

from ws import forms, waivers
from ws.decorators import participant_or_anon


class PayDuesView(FormView):
    """ Allow members to purchase a membership for an email address.

    NOTE: This view only *displays* the form. If users attempt
    to POST directly to the route, nothing will happen.

    Memberships are linked to email addresses. It's possible to purchase a
    membership for somebody else, or to purchase one without a trips account.
    """

    template_name = 'profile/membership.html'
    form_class = forms.DuesForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['participant'] = self.request.participant
        return kwargs

    def post(self, request, *args, **kwargs):
        """ Inform users that posting the form is not allowed.

        Instead, form contents should be submitted to CyberSource.
        """
        # As for why we need this:
        # FormView supplies both GET and POST implementations.
        # It's not possible to use just the GET implementation without POST.
        return HttpResponseNotAllowed(["GET"])

    @method_decorator(participant_or_anon)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class SignWaiverView(FormView):
    template_name = 'profile/waiver.html'
    form_class = forms.WaiverForm
    success_url = reverse_lazy('home')

    def send_waiver(
        self, releasor: Optional[waivers.Person], guardian: Optional[waivers.Person],
    ):
        email, embedded_url = waivers.initiate_waiver(
            participant=self.request.participant,  # type:ignore
            releasor=releasor,
            guardian=guardian,
        )
        if not embedded_url:  # Will be sent by email
            messages.success(self.request, f"Waiver sent to {email}")
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

    def guardian_from_form(self) -> Optional[waivers.Person]:
        """ Build a Person object from the optional guardian form.

        Only participants who are minors need to supply their guardian.
        This method should only be invoked for minors.

        NB: If the form is invalid, we'll assume no guardian.
        This is a shortcut we take because:

        1. Supporting form validation on multiple forms can be a pain
        2. Maybe one or two people a year need the guardian feature
        3. Frontend form validation takes care of validating two fields present
        """
        guardian_form = self.get_guardian_form()
        if guardian_form.is_valid():
            return waivers.Person(
                name=guardian_form.cleaned_data['name'],
                email=guardian_form.cleaned_data['email'],
            )
        return None

    def form_valid(self, form):
        """ Handle a name & email (plus perhaps guardian) submission from anonymous users.

        Authenticated users with a participant record can just use the overridden post()
        """
        releasor: Optional[waivers.Person] = None

        # When there's a participant object, we'll just use that as releasor
        # (We'll bypass form validation for participants, but handle just in case)
        if not self.request.participant:  # pragma: no cover, type: ignore
            releasor = waivers.Person(
                name=form.cleaned_data['name'], email=form.cleaned_data['email']
            )

        return self.send_waiver(releasor=releasor, guardian=self.guardian_from_form())

    def post(self, request, *args, **kwargs):
        """ Either use participant or a name+email form to submit a waiver. """
        # The user is logged in as a participant; we can bypass normal form validation
        # (the user need not give their name & email)
        if request.participant:
            return self.send_waiver(releasor=None, guardian=self.guardian_from_form())

        # The user is not logged in, and must submit a valid form with name & email
        return super().post(request, *args, **kwargs)

    @method_decorator(participant_or_anon)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)
