"""Signup views.

The "signup" object is the core way in which trips are organized. To express
interest in a lottery trip, a participant "signs up" in the UI. This creates a
SignUp object, with `on_trip=False` (since the participant is not yet on the
trip). When the lottery algorithm runs, the participant may be placed on the
trip (`on_trip=True`). Depending on the particular algorithm, participants that
were not awarded a spot on the trip may have a waitlist entry created for them.
"""

from django import db
from django import forms as django_forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.forms import HiddenInput
from django.forms.utils import ErrorList
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DeleteView

from ws import forms, models
from ws.decorators import group_required, user_info_required
from ws.mixins import LotteryPairingMixin
from ws.utils.membership import reasons_cannot_attend


class BaseSignUpView(CreateView, LotteryPairingMixin):
    template_name = "trips/signup.html"

    # Both model & form class will be overridden by children
    model: type[db.models.Model]
    form_class: type[django_forms.ModelForm]

    @property
    def participant(self):
        return self.request.participant

    def get_form(self, form_class=None):
        signup_form = super().get_form(form_class)
        signup_form.fields["trip"].widget = HiddenInput()
        return signup_form

    def form_valid(self, form):
        signup = form.save(commit=False)
        signup.participant = self.request.participant

        errors = self.get_errors(signup)
        if errors:
            form.errors["__all__"] = ErrorList(errors)
            return self.form_invalid(form)
        return super().form_valid(form)

    def get_errors(self, signup):
        """Take a signup (saved, but not committed), and validate."""
        errors = []
        # (user_info_required ensures that participant is present & not None)
        if signup.trip in signup.participant.trip_set.all():
            errors.append("Already signed up for this trip!")
        if signup.participant in signup.trip.leaders.all():
            errors.append("Already a leader on this trip!")

        # (Use the high-level utility method that enforces a cache refresh if necessary)
        errors.extend(
            reason.label
            for reason in reasons_cannot_attend(self.request.user, signup.trip)
        )
        return errors

    def get_success_url(self):
        trip = self.object.trip
        msg = "Signed up!"

        # If the lottery will run in single-trip mode,
        # inform participants about pairing effects
        if trip.single_trip_pairing and self.reciprocally_paired:
            msg += f" You're paired with {self.paired_par.name}."
            if trip.signup_set.filter(participant=self.paired_par).exists():
                msg += " The lottery will attempt to place you together."
            else:
                msg += (
                    " If they do not sign up for this trip, the lottery"
                    " will attempt to place you alone on this trip."
                )

        messages.success(self.request, msg)

        return reverse("view_trip", args=(trip.pk,))


class LeaderSignUpView(BaseSignUpView):
    model = models.LeaderSignUp
    form_class = forms.LeaderSignUpForm

    def get_errors(self, signup):
        errors = super().get_errors(signup)
        trip = signup.trip
        if not signup.participant.can_lead(trip.program_enum):
            errors.append(f"Can't lead {trip.get_program_display()} trips!")
        if not trip.allow_leader_signups:
            errors.append("Trip is not currently accepting leader signups.")
        if models.LeaderSignUp.objects.filter(
            trip=signup.trip, participant=signup.participant
        ).exists():
            errors.append(
                "Already signed up as a leader on this trip! "
                "Contact the trip organizer to be re-added."
            )
        return errors

    @method_decorator(group_required("leaders"))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class SignUpView(BaseSignUpView):
    """Special view designed to be accessed only on invalid signup form

    The "select trip" field is hidden, as this page is meant to be accessed
    only from a Trip-viewing page. Technically, by manipulating POST data on
    the hidden field (Trip), participants could sign up for any trip this way.
    This is not really an issue, though, so no security flaw.
    """

    model = models.SignUp
    form_class = forms.SignUpForm

    def get_errors(self, signup):
        errors = super().get_errors(signup)

        # Guard against direct POST
        # (Form is normally hidden by display logic, but this enforces rules)
        if not signup.trip.signups_open:  # Guards against direct POST
            errors.append("Signups aren't open!")
        return errors

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class DeleteSignupView(DeleteView):
    model = models.SignUp
    success_url = reverse_lazy("trips")

    def get(self, request, *args, **kwargs):
        """Request is valid, but method is not (use POST)."""
        messages.warning(self.request, "Use delete button to remove signups.")
        trip = self.get_object().trip
        return redirect(reverse("view_trip", args=(trip.pk,)))

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        signup = self.get_object()
        if not signup.participant == request.participant:
            raise PermissionDenied
        trip = signup.trip
        drops_allowed = trip.let_participants_drop or (
            trip.upcoming and trip.algorithm == "lottery"
        )
        if not drops_allowed:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
