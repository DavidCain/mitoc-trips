"""Participant preference views.

Users can enroll in discounts, rank their preferred trips, or elect to be
paired with another participant. All of these options are deemed "preferences"
of the participant.
"""
import contextlib
import json
from datetime import datetime
from typing import Any

from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, FormView, TemplateView

from ws import enums, forms, models, tasks, unsubscribe
from ws.decorators import participant_required, user_info_required
from ws.mixins import LotteryPairingMixin
from ws.utils.dates import is_currently_iap, local_date


class LotteryPairingView(CreateView, LotteryPairingMixin):
    model = models.LotteryInfo
    template_name = "preferences/lottery/pairing.html"
    form_class = forms.LotteryPairForm
    success_url = reverse_lazy("lottery_preferences")

    def get_context_data(self, **kwargs):
        """Get a list of all other participants who've requested pairing."""
        context = super().get_context_data(**kwargs)
        self.participant = self.request.participant
        context["pair_requests"] = self.pair_requests
        context["currently_winter_school"] = is_currently_iap()
        return context

    def get_form_kwargs(self):
        """Edit existing instance, prevent user from pairing with self."""
        kwargs = super().get_form_kwargs()
        kwargs["participant"] = participant = self.request.participant
        with contextlib.suppress(models.LotteryInfo.DoesNotExist):
            kwargs["instance"] = participant.lotteryinfo

        return kwargs

    def form_valid(self, form):
        participant = self.request.participant
        lottery_info = form.save(commit=False)
        lottery_info.participant = participant
        self.add_pairing_messages()
        return super().form_valid(form)

    def add_pairing_messages(self):
        """Add messages that explain next steps for lottery pairing."""
        self.participant = self.request.participant
        paired_par = self.paired_par

        if not paired_par:
            no_pair_msg = "Requested normal behavior (no pairing) in lottery"
            messages.success(self.request, no_pair_msg)
            return

        reciprocal = self.reciprocally_paired

        pre = "Successfully paired" if reciprocal else "Requested pairing"
        messages.success(self.request, f"{pre} with {paired_par}")

        if reciprocal:
            msg = (
                "You must both sign up for trips you're interested in: "
                "you'll only be placed on a trip if you both signed up. "
                "Either one of you can rank the trips."
            )
            messages.info(self.request, msg)
        else:
            msg = f"{paired_par} must also select to be paired with you."
            messages.info(self.request, msg)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class DiscountsView(FormView):
    form_class = forms.DiscountForm
    template_name = "preferences/discounts.html"
    success_url = reverse_lazy("discounts")

    def get_queryset(self):
        available = Q(active=True)
        par = self.request.participant
        if not (par and par.is_student):
            available &= Q(student_required=False)
        return models.Discount.objects.filter(available)

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["discounts"].queryset = self.get_queryset().order_by("name")
        return form

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.participant
        return kwargs

    def form_valid(self, form):
        participant = form.save()
        for discount in participant.discounts.all():
            tasks.update_discount_sheet_for_participant.delay(
                discount.pk, participant.pk
            )

        if participant.membership and participant.membership.membership_active:
            messages.success(self.request, "Discount choices updated!")
        else:
            messages.error(
                self.request,
                "You must be a current MITOC member to receive discounts. "
                "We recorded your discount choices, but please pay dues to be eligible",
            )
            return redirect(reverse("pay_dues"))

        return super().form_valid(form)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class LotteryPreferencesView(TemplateView, LotteryPairingMixin):
    template_name = "preferences/lottery/edit.html"
    update_msg = "Lottery preferences updated"
    car_prefix = "car"

    @property
    def post_data(self):
        return json.loads(self.request.body) if self.request.method == "POST" else None

    @property
    def ranked_signups(self):
        # NOTE: In the future, we may support multi-trip lotteries outside WS
        # For now, though, this tool is only for ranking WS trips
        return (
            models.SignUp.objects.filter(
                participant=self.request.participant,
                on_trip=False,
                trip__algorithm="lottery",
                trip__program=enums.Program.WINTER_SCHOOL.value,
                trip__trip_date__gt=local_date(),
            )
            .order_by("order", "time_created", "pk")
            .select_related("trip")
        )

    @property
    def ranked_signups_dict(self):
        """Used by the Angular trip-ranking widget."""
        return [
            {"id": s.pk, "trip": {"id": s.trip.pk, "name": s.trip.name}}
            for s in self.ranked_signups
        ]

    def get_lottery_form(self):
        participant = self.request.participant
        try:
            lottery_info = participant.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            lottery_info = None
        return forms.LotteryInfoForm(self.post_data, instance=lottery_info)

    def get_context_data(self, **kwargs):
        self.participant = self.request.participant
        lottery_form = self.get_lottery_form()

        return {
            "currently_winter_school": is_currently_iap(),
            "ranked_signups": list(
                self.ranked_signups.values("id", "trip__id", "trip__name")
            ),
            "lottery_form": lottery_form,
            # Avoid a redundant query! (We'll show full pairing info separately)
            "has_paired_par": bool(
                lottery_form.instance and lottery_form.instance.paired_with_id
            ),
        }

    def post(self, request, *args, **kwargs):
        context = self.get_context_data()
        lottery_form = context["lottery_form"]
        if not lottery_form.is_valid():
            # Could use lottery_form.errors to give a better message...
            return JsonResponse({"message": "Lottery form invalid"}, status=400)

        lottery_info = lottery_form.save(commit=False)
        lottery_info.participant = self.request.participant
        if lottery_info.car_status == "none":
            lottery_info.number_of_passengers = None
        lottery_info.save()

        try:
            self.save_signups()
        except (ValueError, TypeError):
            return JsonResponse({"message": "Unable to save signups"}, status=400)

        self.handle_paired_signups()
        return JsonResponse({"message": self.update_msg}, status=200)

    def save_signups(self) -> None:
        """Save the rankings given by the participant, optionally removing any signups."""
        par: models.Participant = self.request.participant  # type: ignore[attr-defined]
        posted_signups = self.post_data["signups"]
        required_fields: set[str] = {"id", "deleted", "order"}

        for ps in posted_signups:
            for key in required_fields:
                if key not in ps:
                    raise ValueError(f"{key} missing from {ps}")

        # First, delete any signups (provided they belong to the user & are lottery WS trips)
        # It's important that we prevent participants from deleting *other* signups with this route:
        # 1. Not all trips allow participants to drop off
        # 2. Signals aren't triggered from this `delete()`, which means FCFS logic isn't triggered
        to_del_ids = [p["id"] for p in posted_signups if p["deleted"]]
        if to_del_ids:
            self.ranked_signups.filter(pk__in=to_del_ids).delete()

        # Next, explicitly rank signups that the participant listed
        order_per_signup: dict[int, int] = {
            int(p["id"]): int(p["order"]) for p in posted_signups if not p["deleted"]
        }
        signups = models.SignUp.objects.filter(participant=par, pk__in=order_per_signup)
        for signup in signups:
            signup.order = order_per_signup[signup.pk]
        models.SignUp.objects.bulk_update(signups, ["order"])

    def handle_paired_signups(self):
        """For participants who might be paired, warn if other participant hasn't signed up.

        We can only place paired participants on a trip together if *both* of them have signed up.
        Accordingly, any paired participant trying to rank a trip for the two of them will be
        warned if the other half of the pairing hasn't signed up yet.
        """
        if not self.reciprocally_paired:
            return

        paired_par = self.paired_par
        # Don't just iterate through saved forms. This could miss signups
        # that participant ranks, then the other signs up for later
        for signup in self.ranked_signups:
            trip = signup.trip
            try:
                pair_signup = models.SignUp.objects.get(
                    participant=paired_par, trip=trip
                )
            except models.SignUp.DoesNotExist:
                msg = f"{paired_par} hasn't signed up for {trip}."
                messages.warning(self.request, msg)
            else:
                pair_signup.order = signup.order
                pair_signup.save()

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class EmailPreferencesView(CreateView):
    """Let participants choose what sorts of emails are sent to them.

    For now, this just controls membership reminders.
    In the future, we might support controlling other types of emails.
    """

    form_class = forms.EmailPreferencesForm
    template_name = "preferences/email/edit.html"
    success_url = reverse_lazy("home")

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            "instance": self.request.participant,
        }

    # Most views require up-to-date participant information.
    # However, making people give us information just to opt out of emails is annoying.
    @method_decorator(participant_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def _message(self, send_membership_reminder: bool) -> str:
        """Explain to end users when/if email reminders will be sent."""
        if not send_membership_reminder:
            return "Will not send any emails reminding you to remind your membership."

        participant = self.request.participant  # type:ignore[attr-defined]
        if not participant.membership:
            return "If you sign up for a membership, we'll remind you when it's time to renew."

        date_to_remind = participant.membership.date_when_renewal_is_recommended(
            report_past_dates=False
        )
        if date_to_remind:
            renewal = datetime.strftime(date_to_remind, "%b %-d, %Y")
            return f"We'll send you an email on {renewal} reminding you to renew."

        return "If you have an active membership, we'll remind you when it's time to renew."

    def form_valid(self, form):
        messages.success(
            self.request, self._message(form.cleaned_data["send_membership_reminder"])
        )

        return super().form_valid(form)


class EmailUnsubscribeView(TemplateView):
    """Allow unsubscribing whether or not the user is logged in!"""

    template_name = "preferences/email/unsubscribe.html"
    success_url = reverse_lazy("email_preferences")

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        token: str = self.kwargs["token"]

        participant: models.Participant | None = request.participant  # type: ignore[attr-defined]

        try:
            unsubscribed_par = unsubscribe.unsubscribe_from_token(token)
        except unsubscribe.InvalidTokenError as e:
            messages.add_message(request, messages.ERROR, str(e))
            if participant:
                # NOTE: we *could* just say "oh, hey, you're logged in - we'll just unsubscribe you."
                # However, we can't be totally sure that the logged-in participant is the same as the token.
                # To keep things simple, just have users handle this themselves
                messages.add_message(
                    request,
                    messages.INFO,
                    "However, you are logged in and can directly edit your mail preferences.",
                )
        else:
            messages.add_message(request, messages.SUCCESS, "Successfully unsubscribed")
            # This should hopefully be a very rare edge case.
            if participant and unsubscribed_par.pk != participant.pk:
                messages.add_message(
                    request,
                    messages.WARNING,
                    "Note that the unsubscribe token was for a different participant! "
                    "You may edit your own mail preferences below.",
                )

        # If the participant is logged-in, we should redirect them to the preferences view.
        # In the usual case, this lets users see that they're unsubscribed, and manage prefs directly.
        # This redirect also handles various edge cases:
        # - Invalid token, but since they're logged in, they can just use the form
        # - Participant in the token was deleted, but viewer is logged in, can use the form
        # - Token was valid, but for another participant than the one that's logged in!
        if participant:
            return redirect(reverse("email_preferences"))

        # The viewer is either not logged in, or just lacks a participant record.
        # Just render a plain page with the message and a link to edit email preferences.
        return super().get(request, *args, **kwargs)
