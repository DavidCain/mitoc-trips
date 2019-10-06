from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import FormView

from ws import forms, models, tasks
from ws.mailman.request import write_requests_to_db


class MassUnsubscribeView(FormView):
    template_name = 'mailman/unsubscribe.html'
    form_class = forms.MassUnsubscribeForm
    success_url = reverse_lazy('unsubscribe')

    def get_initial(self):
        initial = super().get_initial().copy()
        if self.request.participant:
            initial['email'] = self.request.participant.email
        return initial

    def _success_messages(self, form):
        mailing_lists = form.cleaned_data['mailing_lists']
        email = form.cleaned_data['email']
        target = ', '.join(f'{name}@mit.edu' for name in mailing_lists)
        if len(target) > 80:
            target = f'{len(mailing_lists)} mailing lists'
        messages.success(self.request, f"Requested unsubscription from {target}.")

        messages.info(
            self.request, f"Check your inbox at {email} for confirmation links!"
        )

    def get_context_data(self, **kwargs):
        if not self.request.user.is_authenticated:
            return super().get_context_data(**kwargs)

        existing = (
            models.MailingListRequest.objects.filter(
                requested_by=self.request.user,
                action=models.MailingListRequest.Action.UNSUBSCRIBE,
            )
            # Just display the newest request per mailing list.
            # If a previous request failed or was successful, that's not really relevant.
            # (User may have since re-subscribed, for example)
            .order_by('mailing_list', 'email', '-time_created').distinct(
                'mailing_list', 'email'
            )
        )  # Hopefully not ever relevant, but avoid massive queries

        return {
            'existing_requests': existing[:250],  # (Guard against huge queries)
            **super().get_context_data(**kwargs),
        }

    def form_valid(self, form):
        email = form.cleaned_data['email']
        write_requests_to_db(
            email=email,
            mailing_lists=form.cleaned_data['mailing_lists'],
            requested_by=self.request.user,
        )

        tasks.handle_unsubscribe_requests.delay(email)

        self._success_messages(form)
        return super().form_valid(form)
