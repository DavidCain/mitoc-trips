from collections import defaultdict
import json

from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.forms import HiddenInput
from django.forms.models import model_to_dict
from django.forms.utils import ErrorList
from django.http import Http404, JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import (CreateView, DetailView, DeleteView, FormView,
                                  ListView, TemplateView, UpdateView, View)
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import FormMixin

from allauth.account.views import PasswordChangeView

from ws import forms
from ws import models
from ws.decorators import group_required, user_info_required, admin_only, chairs_only
from ws.lottery import SingleTripLotteryRunner
from ws import message_generators
from ws import tasks
from ws.templatetags.trip_tags import annotated_for_trip_list

from ws.utils.dates import (local_date, local_now, is_winter_school, ws_year,
                            itinerary_available_at)
from ws.utils.model_dates import ws_lectures_complete
import ws.utils.perms as perm_utils
import ws.utils.ratings as ratings_utils
import ws.utils.signups as signup_utils


class TripLeadersOnlyView(View):
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        """ Only allow creator, leaders of the trip, and chairs. """
        trip = self.get_object()
        chair = perm_utils.chair_or_admin(request.user, trip.activity)
        trip_leader = perm_utils.leader_on_trip(request.participant, trip, True)
        if not (chair or trip_leader):
            return render(request, 'not_your_trip.html', {'trip': trip})
        return super().dispatch(request, *args, **kwargs)


class LoginAfterPasswordChangeView(PasswordChangeView):
    @property
    def success_url(self):
        return reverse_lazy('account_login')


login_after_password_change = login_required(LoginAfterPasswordChangeView.as_view())


class OtherParticipantView(SingleObjectMixin):
    @property
    def user(self):
        return self.participant.user

    @property
    def participant(self):
        if not hasattr(self, 'object'):
            self.object = self.get_object()
        return self.object


class DeleteParticipantView(OtherParticipantView, DeleteView):
    model = models.Participant
    success_url = reverse_lazy('participant_lookup')

    def delete(self, request, *args, **kwargs):
        redir = super().delete(request, *args, **kwargs)
        self.user.delete()
        return redir

    @method_decorator(admin_only)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ParticipantEditMixin(TemplateView):
    """ Updates a participant. Requires self.participant and self.user. """
    template_name = 'profile/edit.html'
    update_msg = 'Personal information updated successfully'

    @property
    def user(self):
        raise NotImplementedError

    @property
    def has_car(self):
        return 'has_car' in self.request.POST

    def prefix(self, base, **kwargs):
        return dict(prefix=base, scope_prefix=base + '_scope', **kwargs)

    def get_context_data(self, *args, **kwargs):
        """ Return a dictionary primarily of forms to for template rendering.
        Also includes a value for the "I have a car" checkbox.

        Outputs three types of forms:
            - Bound forms, if POSTed
            - Empty forms if GET, and no stored Participant data
            - Filled forms if GET, and Participant data exists

        Forms are bound to model instances for UPDATE if such instances exist.
        """
        post = self.request.POST if self.request.method == "POST" else None
        participant = self.participant

        # Access other models within participant
        car = participant and participant.car
        e_info = participant and participant.emergency_info
        e_contact = e_info and e_info.emergency_contact

        # If no Participant object, fill at least with User email
        par_kwargs = self.prefix("participant", instance=participant)
        par_kwargs["user"] = self.user
        if not participant:
            par_kwargs["initial"] = {'email': self.user.email}

        context = {
            'currently_has_car': bool(car),
            'participant_form': forms.ParticipantForm(post, **par_kwargs),
            'car_form': forms.CarForm(post, instance=car, **self.prefix('car')),
            'emergency_info_form': forms.EmergencyInfoForm(post, instance=e_info, **self.prefix('einfo')),
            'emergency_contact_form': forms.EmergencyContactForm(post, instance=e_contact, **self.prefix('econtact')),
        }

        # Boolean: Already responded to question.
        # None: has not responded yet
        if post:
            context['has_car_checked'] = self.has_car
        elif participant:
            context['has_car_checked'] = bool(participant.car)
        else:
            context['has_car_checked'] = None

        return context

    def post(self, request, *args, **kwargs):
        """ Validate POSTed forms, except CarForm if "no car" stated.

        Upon validation, redirect to homepage or `next` url, if specified.
        """
        context = self.get_context_data()
        required_dict = {key: val for key, val in context.items()
                         if isinstance(val, forms.NgModelForm)}

        if not self.has_car:
            required_dict.pop('car_form')
            context['car_form'] = forms.CarForm()  # Avoid validation errors

        if all(form.is_valid() for form in required_dict.values()):
            self._save_forms(self.user, required_dict)
            if self.participant == self.request.participant:
                messages.success(request, self.update_msg)
            return self.success_redirect()
        else:
            return render(request, self.template_name, context)

    def _save_forms(self, user, post_forms):
        """ Given completed, validated forms, handle saving all.

        If no CarForm is supplied, a participant's existing car will be removed.

        :param post_forms: Dictionary of <template_name>: <form>
        """
        e_contact = post_forms['emergency_contact_form'].save()
        e_info = post_forms['emergency_info_form'].save(commit=False)
        e_info.emergency_contact = e_contact
        e_info = post_forms['emergency_info_form'].save()

        participant = post_forms['participant_form'].save(commit=False)
        participant.user_id = user.id
        participant.emergency_info = e_info

        del_car = False
        try:
            car = post_forms['car_form'].save()
        except KeyError:  # No CarForm posted
            # If Participant existed and has a stored Car, mark it for deletion
            if participant.car:
                car = participant.car
                participant.car = None
                del_car = True
        else:
            participant.car = car

        participant.save()
        if del_car:
            car.delete()

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def success_redirect(self):
        return redirect(self.request.GET.get('next', 'home'))


class EditParticipantView(ParticipantEditMixin, OtherParticipantView):
    model = models.Participant

    @property
    def user(self):
        return self.participant.user

    def success_redirect(self):
        return redirect(reverse('view_participant', args=(self.participant.id,)))

    @method_decorator(admin_only)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class EditProfileView(ParticipantEditMixin):
    @property
    def user(self):
        return self.request.user

    @property
    def participant(self):
        return self.request.participant


class ParticipantLookupView(TemplateView, FormView):
    template_name = 'participants/view.html'
    form_class = forms.ParticipantLookupForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['user_viewing'] = False
        context['lookup_form'] = self.get_form(self.form_class)
        return context

    def form_valid(self, lookup_form):
        participant = lookup_form.cleaned_data['participant']
        return redirect(reverse('view_participant', args=(participant.id,)))

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class LotteryPairingMixin(object):
    """ Gives information about lottery pairing.

    Requires a `participant` attribute.
    """
    @property
    def pair_requests(self):
        requested = Q(lotteryinfo__paired_with=self.participant)
        return models.Participant.objects.filter(requested)

    @property
    def paired_par(self):
        try:
            return self.participant.lotteryinfo.paired_with
        except ObjectDoesNotExist:  # No lottery info for paired participant
            return None

    @property
    def reciprocally_paired(self):
        """ Return if the participant is reciprocally paired with another. """
        paired_par = self.paired_par
        if paired_par:
            try:
                return paired_par.lotteryinfo.paired_with == self.participant
            except ObjectDoesNotExist:
                return False
        return False


class LectureAttendanceMixin:
    """ Manage the participant's lecture attendance. """
    def can_set_attendance(self, participant):
        # WS chairs can set any time for any user
        if perm_utils.is_chair(self.request.user, 'winter_school', True):
            return True

        # Non-chairs are only allowed during WS when setting enabled
        if not is_winter_school():
            return False
        settings = models.WinterSchoolSettings.load()
        if not settings.allow_setting_attendance:
            return False

        # Non-chairs may only set attendance for themselves
        return participant == self.request.participant


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


class ParticipantView(ParticipantLookupView, SingleObjectMixin,
                      LotteryPairingMixin, LectureAttendanceMixin):
    model = models.Participant
    context_object_name = 'participant'

    def get_queryset(self):
        participant = super().get_queryset()
        return participant.select_related('emergency_info__emergency_contact')

    def get_trips(self):
        participant = self.object or self.get_object()

        today = local_date()

        # reusable Query objects
        is_par = Q(signup__participant=participant)
        par_on_trip = is_par & Q(signup__on_trip=True)
        leading_trip = Q(leaders=participant)
        in_future = Q(trip_date__gte=today)
        in_past = Q(trip_date__lt=today)

        # Prefetch data to avoid n+1 queries enumerating trips
        prefetches = ['leaders__leaderrating_set']

        # Trips where the user was participating
        trips = models.Trip.objects.filter(is_par).prefetch_related(*prefetches)
        accepted = trips.filter(par_on_trip)
        waitlisted = trips.filter(is_par, signup__waitlistsignup__isnull=False)

        trips_led = participant.trips_led.prefetch_related(*prefetches)
        trips_created = (models.Trip.objects.filter(creator=participant)
                         .prefetch_related(*prefetches))

        # Avoid doubly-listing trips where they participated or led the trip
        created_but_not_on = trips_created.exclude(leading_trip | par_on_trip)

        return {
            'current': {
                'on_trip': accepted.filter(in_future),
                'waitlisted': waitlisted.filter(in_future),
                'leader': trips_led.filter(in_future),
                'creator': created_but_not_on.filter(in_future),
            },
            'past': {
                'on_trip': accepted.filter(in_past),
                'leader': trips_led.filter(in_past),
                'creator': created_but_not_on.filter(in_past),
            },
        }

    def get_stats(self, trips):
        num_attended = len(trips['past']['on_trip'])
        num_led = len(trips['past']['leader'])
        num_created = len(trips['past']['creator'])
        if not (num_attended or num_led):
            return []

        def pluralize(count):
            return '' if count == 1 else 's'

        stats = ["Attended {} trip".format(num_attended) + pluralize(num_attended),
                 "Led {} trip".format(num_led) + pluralize(num_led)]
        if num_created:
            label = "Created (but wasn't on) {} trip".format(num_created)
            stats.append(label + pluralize(num_created))
        return stats

    def include_pairing(self, context):
        self.participant = self.object
        context['reciprocally_paired'] = self.reciprocally_paired
        context['paired_par'] = self.paired_par
        paired_id = {'pk': self.paired_par.pk} if self.paired_par else {}
        context['pair_requests'] = self.pair_requests.exclude(**paired_id)

    def get_context_data(self, **kwargs):
        participant = self.object = self.get_object()
        user_viewing = self.request.participant == participant

        context = super().get_context_data(**kwargs)

        can_set_attendance = self.can_set_attendance(participant)
        context['can_set_attendance'] = can_set_attendance
        context['show_attendance'] = can_set_attendance or (is_winter_school() and ws_lectures_complete())

        context['user_viewing'] = user_viewing
        if user_viewing:
            user = self.request.user
        else:
            user = participant.user
        context['par_user'] = user

        context['trips'] = trips = self.get_trips()
        context['stats'] = self.get_stats(trips)
        self.include_pairing(context)

        e_info = participant.emergency_info
        e_contact = e_info.emergency_contact
        context['emergency_info_form'] = forms.EmergencyInfoForm(instance=e_info)
        context['emergency_contact_form'] = forms.EmergencyContactForm(instance=e_contact)
        context['participant'] = participant
        if not user_viewing:
            feedback = participant.feedback_set.select_related('trip', 'leader')
            feedback = feedback.prefetch_related('leader__leaderrating_set')
            context['all_feedback'] = feedback
        context['ratings'] = participant.ratings(rating_active=True)

        chair_activities = set(perm_utils.chair_activities(user))
        context['chair_activities'] = [
            label for (activity, label) in models.LeaderRating.ACTIVITY_CHOICES
            if activity in chair_activities
        ]

        if participant.car:
            context['car_form'] = forms.CarForm(instance=participant.car)
        return context

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ParticipantDetailView(ParticipantView, FormView, DetailView):
    def dispatch(self, request, *args, **kwargs):
        if request.participant == self.get_object():
            return redirect(reverse('home'))
        return super().dispatch(request, *args, **kwargs)


class ProfileView(ParticipantView):
    def get(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            today = local_date()
            current_trips = models.Trip.objects.filter(trip_date__gte=today)
            trips = annotated_for_trip_list(current_trips)
            return render(request, 'home.html', {'current_trips': trips})
        elif not request.participant:
            return redirect(reverse('edit_profile'))

        message_generators.warn_if_needs_update(request)
        message_generators.complain_if_missing_feedback(request)

        lottery_messages = message_generators.LotteryMessages(request)
        lottery_messages.supply_all_messages()
        return super().get(request, *args, **kwargs)

    def get_object(self):
        self.kwargs['pk'] = self.request.participant.id
        return super().get_object()

    # Login is not required - we'll handle that in `get()`
    def dispatch(self, request, *args, **kwargs):
        return View.dispatch(self, request, *args, **kwargs)


class BaseSignUpView(CreateView, LotteryPairingMixin):
    model = None
    form_class = None  # Will be overridden by children
    template_name = 'trips/signup.html'

    @property
    def participant(self):
        return self.request.participant

    def get_form(self, form_class=None):
        signup_form = super().get_form(form_class)
        signup_form.fields['trip'].widget = HiddenInput()
        return signup_form

    def get_success_url(self):
        trip = self.object.trip
        msg = "Signed up!"

        # If the lottery will run in single-trip mode,
        # inform participants about pairing effects
        if trip.single_trip_pairing and self.reciprocally_paired:
            msg += " You're paired with {}.".format(self.paired_par.name)
            if trip.signup_set.filter(participant=self.paired_par).exists():
                msg += " The lottery will attempt to place you together."
            else:
                msg += (" If they do not sign up for this trip, the lottery"
                        " will attempt to place you alone on this trip.")

        messages.success(self.request, msg)

        return reverse('view_trip', args=(trip.pk,))


class LeaderSignUpView(BaseSignUpView):
    model = models.LeaderSignUp
    form_class = forms.LeaderSignUpForm

    def form_valid(self, form):
        """ After is_valid() and some checks, assign participant. """
        signup = form.save(commit=False)
        signup.participant = self.request.participant

        errors = []
        if not signup.participant.can_lead(signup.trip.activity):
            errors.append("Can't lead {} trips!".format(signup.trip.activity))
        if signup.trip in signup.participant.trip_set.all():
            errors.append("Already a participant on this trip!")
        if signup.participant in signup.trip.leaders.all():
            errors.append("Already a leader on this trip!")

        if errors:
            form.errors['__all__'] = ErrorList(errors)
            return self.form_invalid(form)
        return super().form_valid(form)

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class SignUpView(BaseSignUpView):
    """ Special view designed to be accessed only on invalid signup form

    The "select trip" field is hidden, as this page is meant to be accessed
    only from a Trip-viewing page. Technically, by manipulating POST data on
    the hidden field (Trip), participants could sign up for any trip this way.
    This is not really an issue, though, so no security flaw.
    """
    model = models.SignUp
    form_class = forms.SignUpForm

    def form_valid(self, form):
        """ After is_valid() and some checks, assign participant from User.

        If the participant has signed up before, halt saving, and return
        a form with errors (this shouldn't happen, as a template should
        prevent the form from being displayed in the first place).
        """
        signup = form.save(commit=False)
        signup.participant = self.request.participant
        if signup.trip in signup.participant.trip_set.all():
            form.errors['__all__'] = ErrorList(["Already signed up!"])
            return self.form_invalid(form)
        elif not signup.trip.signups_open:  # Guards against direct POST
            form.errors['__all__'] = ErrorList(["Signups aren't open!"])
            return self.form_invalid(form)
        return super().form_valid(form)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ItineraryInfoFormMixin(object):
    def get_info_form(self, trip):
        """ Return a stripped form for read-only display.

        Drivers will be displayed separately, and the 'accuracy' checkbox
        isn't needed for display.
        """
        if not trip.info:
            return None
        info_form = forms.TripInfoForm(instance=trip.info)
        info_form.fields.pop('drivers')
        info_form.fields.pop('accurate')
        return info_form


class TripView(DetailView):
    """ Display the trip to both unregistered users and known participants.

    For unregistered users, the page will have minimal information (a description,
    and leader names). For other participants, the controls displayed to them
    will vary depending on their permissions.
    """
    model = models.Trip
    context_object_name = 'trip'
    template_name = 'trips/view.html'

    def get_queryset(self):
        trips = super().get_queryset().select_related('info')
        return trips.prefetch_related('leaders', 'leaders__leaderrating_set')

    def get_participant_signup(self, trip=None):
        """ Return viewer's signup for this trip (if one exists, else None) """
        if not self.request.participant:
            return None
        trip = trip or self.get_object()
        return self.request.participant.signup_set.filter(trip=trip).first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        trip = self.object
        context['can_admin'] = (
            perm_utils.chair_or_admin(self.request.user, trip.activity) or
            perm_utils.leader_on_trip(self.request.participant, trip, True)
        )
        return context

    def post(self, request, *args, **kwargs):
        """ Add signup to trip or waitlist, if applicable.

        Used if the participant has signed up, but wasn't placed.
        """
        signup = self.get_participant_signup()
        signup_utils.trip_or_wait(signup, self.request, trip_must_be_open=True)
        return self.get(request)


class ReviewTripView(DetailView):
    model = models.Trip
    template_name = 'trips/review.html'
    success_msg = "Thanks for your feedback!"

    @property
    def posted_feedback(self):
        """ Convert named fields of POST data to participant -> feedback mapping.

        If the form data was garbled (intentionally or otherwise), this method
        will raise ValueError or TypeError (on either 'split' or `int`)
        """
        for key, comments in self.request.POST.items():
            if not (key.startswith("par_") or key.startswith("flake_")):
                continue

            feedback_type, par_pk = key.split('_')
            showed_up = feedback_type == 'par'

            yield int(par_pk), comments.strip(), showed_up

    def post(self, request, *args, **kwargs):
        """ Create or update all feedback passed along in form data. """
        trip = self.object = self.get_object()
        leader = self.request.participant

        try:
            posted_feedback = list(self.posted_feedback)
        except (TypeError, ValueError):
            # This should never happen, but look at doing this more nicely?
            return HttpResponseBadRequest("Invalid form contents")

        # Create or update feedback for all feedback passed in the form
        existing_feedback = {feedback.participant.pk: feedback
                             for feedback in self.get_existing_feedback()}
        for pk, comments, showed_up in posted_feedback:
            blank_feedback = showed_up and not comments
            existing = feedback = existing_feedback.get(pk)

            if existing and blank_feedback:
                existing.delete()
                continue

            if not existing:
                if blank_feedback:
                    continue  # Don't create new feedback saying nothing useful
                kwargs = {'leader': leader, 'trip': trip,
                          'participant': models.Participant.objects.get(pk=pk)}
                feedback = models.Feedback.objects.create(**kwargs)

            feedback.comments = comments
            feedback.showed_up = showed_up
            feedback.save()

        messages.success(self.request, self.success_msg)
        return redirect(reverse('home'))

    @property
    def trip_participants(self):
        accepted_signups = self.object.signup_set.filter(on_trip=True)
        accepted_signups = accepted_signups.select_related('participant')
        return [signup.participant for signup in accepted_signups]

    def get_existing_feedback(self):
        leader = self.request.participant
        return models.Feedback.everything.filter(trip=self.object, leader=leader)

    @property
    def feedback_list(self):
        feedback = self.get_existing_feedback()
        par_comments = dict(feedback.values_list('participant__pk', 'comments'))
        return [(par, par_comments.get(par.pk, '')) for par in self.trip_participants]

    def get_context_data(self, **kwargs):
        today = local_date()
        trip = self.object = self.get_object()
        return {"trip": trip, "trip_completed": today >= trip.trip_date,
                "feedback_required": trip.activity == 'winter_school',
                "feedback_list": self.feedback_list}

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        if not perm_utils.leader_on_trip(request.participant, trip, False):
            return render(request, 'not_your_trip.html', {'trip': trip})
        return super().dispatch(request, *args, **kwargs)


class AllLeadersView(ListView):
    model = models.Participant
    context_object_name = 'leaders'
    template_name = 'leaders/all.html'

    def get_queryset(self):
        """ Returns all leaders with active ratings. """
        return models.Participant.leaders.get_queryset()

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)

        closed_activities = models.LeaderRating.CLOSED_ACTIVITY_CHOICES
        activities = [(val, label) for (val, label) in closed_activities
                      if val != 'cabin']
        context_data['activities'] = activities
        return context_data

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class LeaderApplicationMixin(ratings_utils.LeaderApplicationMixin):
    """ Superclass for any view involving leader applications.

    (Either participants creating one, or chairs viewing application(s).

    In both cases, we contain the activity in the URL.
    """
    @property
    def activity(self):
        """ The activity, should be verified by the dispatch method. """
        return self.kwargs['activity']

    def get_queryset(self):
        return self.joined_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['activity'] = self.activity
        return context


class ApplicationManager(ratings_utils.ApplicationManager, LeaderApplicationMixin):
    """ Superclass for views where chairs are viewing one or more applications. """
    @property
    def chair(self):
        """ The viewing participant should be an activity chair. """
        return self.request.participant


class LeaderApplyView(LeaderApplicationMixin, CreateView):
    template_name = "leaders/apply.html"
    success_url = reverse_lazy('home')
    form_class = forms.LeaderApplicationForm

    def get_success_url(self):
        return reverse('become_leader', kwargs={'activity': self.activity})

    def get_form_kwargs(self):
        """ Pass the needed "activity" paramater for dynamic form construction. """
        kwargs = super().get_form_kwargs()
        kwargs['activity'] = self.activity
        return kwargs

    def get_queryset(self):
        """ For looking up if any recent applications have been completed. """
        return self.model.objects

    @property
    def par(self):
        return self.request.participant

    def form_valid(self, form):
        """ Link the application to the submitting participant. """
        application = form.save(commit=False)
        application.year = self.application_year
        application.participant = self.par
        rating = self.par.activity_rating(self.activity, rating_active=False)
        application.previous_rating = rating or ''
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        """ Get any existing application and rating. """
        context = super().get_context_data(**kwargs)

        context['year'] = self.application_year
        existing = self.get_queryset().filter(participant=self.par)
        if existing:
            app = existing.order_by('-time_created').first()
            context['application'] = app
            context['can_apply'] = self.can_reapply(app)
        else:
            context['can_apply'] = True
        return context

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        if not models.LeaderApplication.can_apply(kwargs.get('activity')):
            raise Http404
        return super().dispatch(request, *args, **kwargs)


class ApprovedTripsMixin(object):
    model = models.Trip

    @property
    def activity(self):
        return self.kwargs['activity']

    def get_queryset(self):
        """ All upcoming trips of this activity type. """
        return models.Trip.objects.filter(activity=self.activity,
                                          trip_date__gte=local_date())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['activity'] = self.activity
        trips = self.get_queryset()
        context['approved_trips'] = trips.filter(chair_approved=True)
        context['unapproved_trips'] = trips.filter(chair_approved=False)
        return context


class AllLeaderApplicationsView(ApplicationManager, ListView):
    context_object_name = 'leader_applications'
    template_name = 'chair/applications/all.html'

    def get_queryset(self):
        return self.sorted_applications(just_this_year=False)

    def get_context_data(self, **kwargs):
        # Super calls DetailView's `get_context_data` so we'll manually add form
        context = super().get_context_data(**kwargs)

        apps = context['leader_applications']
        context['num_chairs'] = self.num_chairs
        context['needs_rec'] = self.needs_rec(apps)
        context['needs_rating'] = self.needs_rating(apps)
        context['pending'] = context['needs_rating'] or context['needs_rec']

        apps_by_year = defaultdict(list)
        given_rating = apps.filter(num_ratings__gt=0)
        for application in given_rating.order_by('-year', 'participant__name'):
            apps_by_year[application.year].append(application)
        context['apps_by_year'] = [(year, apps_by_year[year])
                                   for year in sorted(apps_by_year, reverse=True)]

        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        activity = kwargs.get('activity')
        if not perm_utils.chair_or_admin(request.user, activity):
            raise PermissionDenied
        if not models.LeaderApplication.can_apply(self.activity):
            context = {'missing_form': True, 'activity': self.activity}
            return render(request, self.template_name, context)
        return super().dispatch(request, *args, **kwargs)


class LeaderApplicationView(ApplicationManager, FormMixin, DetailView):
    """ Handle applications by participants to become leaders. """
    form_class = forms.ApplicationLeaderForm
    context_object_name = 'application'
    template_name = 'chair/applications/view.html'

    def get_success_url(self):
        """ Get the next application in this queue.

        (i.e. if this was an application needing a recommendation,
        move to the next application without a recommendation)
        """
        if self.next_app:  # Set before we saved this object
            app_args = (self.activity, self.next_app.pk)
            return reverse('view_application', args=app_args)
        else:
            return reverse('manage_applications', args=(self.activity,))

    def get_other_apps(self):
        """ Get the applications that come before and after this in the queue.

        Each "queue" is of applications that need recommendations or ratings.
        """
        ordered_apps = iter(self.sorted_applications(just_this_year=True))
        prev_app = None
        for app in ordered_apps:
            if app.pk == self.object.pk:
                try:
                    next_app = next(ordered_apps)
                except StopIteration:
                    next_app = None
                break
            prev_app = app
        else:
            return None, None  # Could be from another (past) year

        def if_valid(other_app):
            mismatch = (not other_app or
                        bool(other_app.num_recs) != bool(app.num_recs) or
                        bool(other_app.num_ratings) != bool(app.num_ratings))
            return None if mismatch else other_app

        return if_valid(prev_app), if_valid(next_app)

    @property
    def par_ratings(self):
        find_ratings = Q(participant=self.object.participant,
                         activity=self.activity)
        return models.LeaderRating.objects.filter(find_ratings)

    @property
    def existing_rating(self):
        return self.par_ratings.filter(active=True).first()

    @property
    def existing_rec(self):
        """ Load an existing recommendation for the viewing participant. """
        find_rec = Q(creator=self.chair,
                     participant=self.object.participant,
                     activity=self.activity,
                     time_created__gte=self.object.time_created)
        return models.LeaderRecommendation.objects.filter(find_rec).first()

    def default_to_recommendation(self):
        """ Whether to default the form to a recommendation or not. """
        return False if self.num_chairs < 2 else not self.existing_rec

    def get_initial(self):
        """ Load an existing rating if one exists.

        Because these applications are supposed to be done with leaders that
        have no active rating in the activity, this should almost always be
        blank.
        """
        initial = {'recommendation': self.default_to_recommendation()}
        existing = self.existing_rating or self.existing_rec
        if existing:
            initial['rating'] = existing.rating
            initial['notes'] = existing.notes
        return initial

    @property
    def assigned_rating(self):
        """ Return any rating given in response to this application. """
        in_future = Q(participant=self.object.participant,
                      activity=self.activity,
                      time_created__gte=self.object.time_created)
        if not hasattr(self, '_assigned_rating'):
            ratings = models.LeaderRating.objects.filter(in_future)
            self._assigned_rating = ratings.order_by('time_created').first()
        return self._assigned_rating

    @property
    def before_rating(self):
        if self.assigned_rating:
            return Q(time_created__lte=self.assigned_rating.time_created)
        else:
            return Q()

    def get_recommendations(self, assigned_rating=None):
        """ Get recommendations made by leaders/chairs for this application.

        Only show recommendations that were made for this application. That is,
        don't show recommendations made before the application was created (they must
        have pertained to a previous appplication), or those created after a
        rating was assigned (those belong to a future application).
        """
        match = Q(participant=self.object.participant, activity=self.activity)
        rec_after_creation = Q(time_created__gte=self.object.time_created)
        find_recs = match & self.before_rating & rec_after_creation
        recs = models.LeaderRecommendation.objects.filter(find_recs)
        return recs.select_related('creator')

    def get_feedback(self):
        """ Return all feedback for the participant.

        Activity chairs see the complete history of feedback (without the normal
        "clean slate" period. The only exception is that activity chairs cannot
        see their own feedback.
        """
        feedback = models.Feedback.everything.filter(
            Q(participant=self.object.participant) & ~Q(participant=self.chair)
        ).select_related('leader', 'trip')

        return feedback.prefetch_related('leader__leaderrating_set')

    def get_context_data(self, **kwargs):
        # Super calls DetailView's `get_context_data` so we'll manually add form
        context = super().get_context_data(**kwargs)
        assigned_rating = self.assigned_rating
        context['assigned_rating'] = assigned_rating
        context['recommendations'] = self.get_recommendations(assigned_rating)
        context['leader_form'] = self.get_form()
        context['all_feedback'] = self.get_feedback()
        context['prev_app'], context['next_app'] = self.get_other_apps()

        participant = self.object.participant
        context['active_ratings'] = list(participant.ratings(rating_active=True))
        context['chair_activities'] = [
            label for (activity, label) in models.LeaderRating.ACTIVITY_CHOICES
            if activity in set(perm_utils.chair_activities(participant.user))
        ]
        context['existing_rating'] = self.existing_rating
        context['existing_rec'] = self.existing_rec

        all_trips_led = self.object.participant.trips_led
        trips_led = all_trips_led.filter(self.before_rating, activity=self.activity)
        context['trips_led'] = trips_led.prefetch_related('leaders__leaderrating_set')
        return context

    def form_valid(self, form):
        """ Save the rating as a recommendation or a binding rating. """
        # After saving, the order of applications changes
        _, self.next_app = self.get_other_apps()  # Obtain next in current order

        rating = form.save(commit=False)
        rating.creator = self.chair
        rating.participant = self.object.participant
        rating.activity = self.object.activity

        is_rec = form.cleaned_data['recommendation']
        if is_rec:
            # Hack to convert the (unsaved) rating to a recommendation
            # (Both models have the exact same fields)
            rec = forms.LeaderRecommendationForm(model_to_dict(rating),
                                                 instance=self.existing_rec)
            rec.save()
        else:
            ratings_utils.deactivate_ratings(rating.participant, rating.activity)
            rating.save()

        fmt = {'verb': "Recommended" if is_rec else "Created",
               'rating': rating.rating, 'participant': rating.participant.name}
        msg = "{verb} {rating} rating for {participant}".format(**fmt)
        messages.success(self.request, msg)

        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        """ Create the leader's rating, redirect to other applications. """
        self.object = self.get_object()
        form = self.get_form()

        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    @method_decorator(chairs_only())
    def dispatch(self, request, *args, **kwargs):
        """ Redirect if anonymous, but deny permission if not a chair. """
        if not perm_utils.chair_or_admin(request.user, self.activity):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class ManageLeadersView(CreateView):
    form_class = forms.LeaderForm
    template_name = 'chair/leaders.html'
    success_url = reverse_lazy('manage_leaders')

    @property
    def allowed_activities(self):
        return perm_utils.chair_activities(self.request.user, True)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['allowed_activities'] = self.allowed_activities
        return kwargs

    def get_initial(self):
        initial = super().get_initial().copy()
        allowed_activities = self.allowed_activities
        if len(allowed_activities) == 1:
            initial['activity'] = allowed_activities[0]
        return initial

    def form_valid(self, form):
        """ Ensure the leader can assign ratings, then apply assigned rating.

        Any existing ratings for this activity will be marked as inactive.
        """
        activity = form.cleaned_data['activity']
        participant = form.cleaned_data['participant']

        # Sanity check on ratings (form hides dissallowed activities)
        if not perm_utils.is_chair(self.request.user, activity, True):
            not_chair = "You cannot assign {} ratings".format(activity)
            form.add_error("activity", not_chair)
            return self.form_invalid(form)

        ratings_utils.deactivate_ratings(participant, activity)

        rating = form.save(commit=False)
        rating.creator = self.request.participant

        msg = "Gave {} rating of '{}'".format(participant, rating.rating)
        messages.success(self.request, msg)
        return super().form_valid(form)

    @method_decorator(chairs_only())
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class CreateTripView(CreateView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = 'trips/create.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['initial'] = kwargs.get('initial', {})
        if not self.request.user.is_superuser:
            allowed_activities = self.request.participant.allowed_activities
            kwargs['allowed_activities'] = allowed_activities

            if is_winter_school() and 'winter_school' in allowed_activities:
                kwargs['initial']['activity'] = 'winter_school'
            else:
                # The first activity may not be open to the leader.
                # We restrict choices, so ensure leader can lead this activity.
                kwargs['initial']['activity'] = kwargs['allowed_activities'][0]
        return kwargs

    def get_success_url(self):
        return reverse('view_trip', args=(self.object.pk,))

    def get_initial(self):
        """ Default with trip creator among leaders. """
        initial = super().get_initial().copy()
        # It's possible for WSC to create trips while not being a leader
        if perm_utils.is_leader(self.request.user):
            initial['leaders'] = [self.request.participant]
        return initial

    def form_valid(self, form):
        """ After is_valid(), assign creator from User, add empty waitlist. """
        creator = self.request.participant
        trip = form.save(commit=False)
        trip.creator = creator
        return super().form_valid(form)

    @method_decorator(group_required('WSC', 'leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class DeleteTripView(DeleteView, TripLeadersOnlyView):
    model = models.Trip
    success_url = reverse_lazy('upcoming_trips')

    def get(self, *args, **kwargs):
        """ Request is valid, but method is not (use POST). """
        messages.warning(self.request, "Use delete button to remove trips.")
        return redirect(reverse('view_trip', kwargs=self.kwargs))


class DeleteSignupView(DeleteView):
    model = models.SignUp
    success_url = reverse_lazy('upcoming_trips')

    def get(self, *args, **kwargs):
        """ Request is valid, but method is not (use POST). """
        messages.warning(self.request, "Use delete button to remove signups.")
        trip = self.get_object().trip
        return redirect(reverse('view_trip', args=(trip.pk,)))

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        signup = self.get_object()
        if not signup.participant == request.participant:
            raise PermissionDenied
        trip = signup.trip
        drops_allowed = (trip.let_participants_drop or
                         (trip.upcoming and trip.algorithm == 'lottery'))
        if not drops_allowed:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class EditTripView(UpdateView, TripLeadersOnlyView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = 'trips/edit.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if not self.request.user.is_superuser:
            allowed_activities = self.request.participant.allowed_activities
            kwargs['allowed_activities'] = allowed_activities
        return kwargs

    @property
    def update_rescinds_approval(self):
        trip = self.object
        return (trip.chair_approved and
                not perm_utils.is_chair(self.request.user, trip.activity) and
                trip.trip_date >= local_date()  # Doesn't matter after trip
                )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['update_rescinds_approval'] = self.update_rescinds_approval
        return context

    def get_success_url(self):
        return reverse('view_trip', args=(self.object.pk,))

    def _ignore_leaders_if_unchanged(self, form):
        """ Don't update the leaders m2m field if unchanged.

        This is a hack to avoid updating the m2m set (normally cleared, then
        reset) Without this, post_add (signal used to send emails) will send
        out a message to all leaders on _every_ trip update.

        A compromise: Only send emails when the leader list is changed.
        See ticket 6707 for an eventual fix to this behavior
        """
        old_pks = {leader.pk for leader in self.object.leaders.all()}
        new_pks = {leader.pk for leader in form.cleaned_data['leaders']}
        if not old_pks.symmetric_difference(new_pks):
            form.cleaned_data.pop('leaders')

    def form_valid(self, form):
        self._ignore_leaders_if_unchanged(form)

        if self.update_rescinds_approval:
            trip = form.save(commit=False)
            trip.chair_approved = False
        return super().form_valid(form)


class TripListView(ListView):
    """ Superclass for any view that displays a list of trips. """
    model = models.Trip
    template_name = 'trips/all/view.html'
    context_object_name = 'trip_queryset'
    form_class = forms.SummaryTripForm

    def get_queryset(self):
        trips = super().get_queryset()
        return annotated_for_trip_list(trips)

    def get_context_data(self, **kwargs):
        """ Sort trips into past and present trips. """
        context_data = super().get_context_data(**kwargs)
        trips = context_data[self.context_object_name]

        today = local_date()
        context_data['current_trips'] = trips.filter(trip_date__gte=today)
        context_data['past_trips'] = trips.filter(trip_date__lt=today)
        return context_data


class UpcomingTripsView(TripListView):
    """ View current trips. Note: currently open to the world!"""
    context_object_name = 'current_trips'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(trip_date__gte=local_date())

    def get_context_data(self, **kwargs):
        # No point sorting into current, past (queryset already handles)
        return super().get_context_data(**kwargs)


class AllTripsView(TripListView):
    """ View all trips, past and present. """
    pass


class ApproveTripsView(UpcomingTripsView):
    template_name = 'trips/all/manage.html'

    def get_queryset(self):
        upcoming_trips = super().get_queryset()
        return upcoming_trips.filter(activity=self.kwargs['activity'])

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        activity = kwargs.get('activity')
        if not perm_utils.is_chair(request.user, activity):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        # No point sorting into current, past (queryset already handles)
        context = super().get_context_data(**kwargs)
        unapproved_trips = self.get_queryset().filter(chair_approved=False)
        context['first_unapproved_trip'] = unapproved_trips.first()
        return context


class LotteryPairingView(CreateView, LotteryPairingMixin):
    model = models.LotteryInfo
    template_name = 'preferences/lottery/pairing.html'
    form_class = forms.LotteryPairForm
    success_url = reverse_lazy('lottery_preferences')

    def get_context_data(self, **kwargs):
        """ Get a list of all other participants who've requested pairing. """
        context = super().get_context_data(**kwargs)
        self.participant = self.request.participant
        context['pair_requests'] = self.pair_requests
        context['is_winter_school'] = is_winter_school()
        return context

    def get_form_kwargs(self):
        """ Edit existing instance, prevent user from pairing with self. """
        kwargs = super().get_form_kwargs()
        kwargs['participant'] = self.request.participant
        kwargs['exclude_self'] = True
        try:
            kwargs['instance'] = self.request.participant.lotteryinfo
        except ObjectDoesNotExist:
            pass
        return kwargs

    def form_valid(self, form):
        participant = self.request.participant
        lottery_info = form.save(commit=False)
        lottery_info.participant = participant
        self.add_pairing_messages()
        return super().form_valid(form)

    def add_pairing_messages(self):
        """ Add messages that explain next steps for lottery pairing. """
        self.participant = self.request.participant
        paired_par = self.paired_par

        if not paired_par:
            no_pair_msg = "Requested normal behavior (no pairing) in lottery"
            messages.success(self.request, no_pair_msg)
            return

        reciprocal = self.reciprocally_paired

        pre = "Successfully paired" if reciprocal else "Requested pairing"
        paired_msg = pre + " with {}".format(paired_par)
        messages.success(self.request, paired_msg)

        if reciprocal:
            msg = ("You must both sign up for trips you're interested in: "
                   "you'll only be placed on a trip if you both signed up. "
                   "Either one of you can rank the trips.")
            messages.info(self.request, msg)
        else:
            msg = "{} must also select to be paired with you.".format(paired_par)
            messages.info(self.request, msg)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class DiscountsView(FormView):
    form_class = forms.DiscountForm
    template_name = 'preferences/discounts.html'
    success_url = reverse_lazy('discounts')

    def get_queryset(self):
        available = Q(active=True)
        par = self.request.participant
        if not (par and par.is_student):
            available &= Q(student_required=False)
        return models.Discount.objects.filter(available)

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        form.fields['discounts'].queryset = self.get_queryset()
        return form

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.request.participant
        return kwargs

    def form_valid(self, discount_form):
        discount_form.save()
        participant = discount_form.save()
        for discount in participant.discounts.all():
            tasks.update_participant.delay(discount.pk, participant.pk)
        msg = ("Discounts updated! Ensure your membership "
               "is active for continued access to discounts.")
        messages.success(self.request, msg)
        return super().form_valid(discount_form)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class LotteryPreferencesView(TemplateView, LotteryPairingMixin):
    template_name = 'preferences/lottery/edit.html'
    update_msg = 'Lottery preferences updated'
    car_prefix = 'car'

    @property
    def post_data(self):
        return json.loads(self.request.body) if self.request.method == "POST" else None

    @property
    def ranked_signups(self):
        today = local_date()
        lotto_signups = Q(participant=self.request.participant,
                          trip__algorithm='lottery', trip__trip_date__gt=today)
        future_signups = models.SignUp.objects.filter(lotto_signups)
        ranked = future_signups.order_by('order', 'time_created')
        return ranked.select_related('trip')

    @property
    def ranked_signups_dict(self):
        """ Used by the Angular trip-ranking widget. """
        return [{'id': s.id, 'trip': {'id': s.trip.id, 'name': s.trip.name}}
                for s in self.ranked_signups]

    def get_car_form(self, use_post=True):
        car = self.request.participant.car
        post = self.post_data if use_post else None
        return forms.CarForm(post, instance=car, scope_prefix=self.car_prefix)

    def get_lottery_form(self):
        try:
            lottery_info = self.request.participant.lotteryinfo
        except ObjectDoesNotExist:
            lottery_info = None
        return forms.LotteryInfoForm(self.post_data, instance=lottery_info)

    def get_context_data(self):
        self.participant = self.request.participant
        return {'is_winter_school': is_winter_school(),
                'ranked_signups': json.dumps(self.ranked_signups_dict),
                'car_form': self.get_car_form(use_post=True),
                'lottery_form': self.get_lottery_form(),
                'reciprocally_paired': self.reciprocally_paired,
                'paired_par': self.paired_par}

    def post(self, request, *args, **kwargs):
        context = self.get_context_data()
        lottery_form = context['lottery_form']
        car_form = context['car_form']
        skip_car_form = lottery_form.data['car_status'] != 'own'
        car_form_okay = skip_car_form or car_form.is_valid()
        if (lottery_form.is_valid() and car_form_okay):
            if skip_car_form:  # New form so submission doesn't show errors
                # (Only needed when doing a Django response)
                context['car_form'] = self.get_car_form(use_post=False)
            else:
                self.request.participant.car = car_form.save()
                self.request.participant.save()
            lottery_info = lottery_form.save(commit=False)
            lottery_info.participant = self.request.participant
            if lottery_info.car_status == 'none':
                lottery_info.number_of_passengers = None
            lottery_info.save()
            self.save_signups()
            self.handle_paired_signups()
            resp, status = {'message': self.update_msg}, 200
        else:
            resp, status = {'message': "Stuff broke"}, 400

        return JsonResponse(resp, status=status)

    def save_signups(self):
        par = self.request.participant
        par_signups = models.SignUp.objects.filter(participant=par)
        posted_signups = self.post_data['signups']

        for post in [p for p in posted_signups if not p['deleted']]:
            signup = par_signups.get(pk=post['id'])
            signup.order = post['order']
            signup.save()
        del_ids = [p['id'] for p in self.post_data['signups'] if p['deleted']]
        if del_ids:
            signup = par_signups.filter(pk__in=del_ids).delete()

    def handle_paired_signups(self):
        if not self.reciprocally_paired:
            return
        paired_par = self.paired_par
        # Don't just iterate through saved forms. This could miss signups
        # that participant ranks, then the other signs up for later
        for signup in self.ranked_signups:
            trip = signup.trip
            try:
                pair_signup = models.SignUp.objects.get(participant=paired_par,
                                                        trip=trip)
            except ObjectDoesNotExist:
                msg = "{} hasn't signed up for {}.".format(paired_par, trip)
                messages.warning(self.request, msg)
            else:
                pair_signup.order = signup.order
                pair_signup.save()

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TripMedical(ItineraryInfoFormMixin):
    def get_cars(self, trip):
        """ Return cars of specified drivers, otherwise all drivers' cars.

        If a trip leader says who's driving in the trip itinerary, then
        only return those participants' cars. Otherwise, gives all cars.
        The template will give a note specifying if these were the drivers
        given by the leader, of if they're all possible drivers.
        """
        signups = trip.signup_set.filter(on_trip=True)
        par_on_trip = (Q(participant__in=trip.leaders.all()) |
                       Q(participant__signup__in=signups))
        cars = models.Car.objects.filter(par_on_trip).distinct()
        if trip.info:
            cars = cars.filter(participant__in=trip.info.drivers.all())
        return cars.select_related('participant__lotteryinfo')

    def get_trip_info(self, trip):
        participants = trip.signed_up_participants.filter(signup__on_trip=True)
        participants = participants.select_related('emergency_info')
        signups = trip.signup_set.filter(on_trip=True)
        signups = signups.select_related('participant__emergency_info')
        return {'trip': trip, 'participants': participants, 'cars': self.get_cars(trip),
                'info_form': self.get_info_form(trip)}


class AllTripsMedicalView(ListView, TripMedical):
    model = models.Trip
    template_name = 'trips/all/medical.html'
    context_object_name = 'trips'
    form_class = forms.SummaryTripForm

    def get_queryset(self):
        trips = super().get_queryset().order_by('trip_date')
        today = local_date()
        return trips.filter(trip_date__gte=today)

    def get_context_data(self, **kwargs):
        context_data = super().get_context_data(**kwargs)
        by_trip = (self.get_trip_info(trip) for trip in self.get_queryset())
        all_trips = [(c['trip'], c['participants'], c['cars'], c['info_form'])
                     for c in by_trip]
        context_data['all_trips'] = all_trips
        return context_data

    @method_decorator(group_required('WSC', 'WIMP'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class TripMedicalView(DetailView, TripLeadersOnlyView, TripMedical):
    queryset = models.Trip.objects.all()
    template_name = 'trips/medical.html'

    def get_context_data(self, **kwargs):
        """ Get a trip info form for display as readonly. """
        trip = self.get_object()
        context_data = self.get_trip_info(trip)
        context_data['participants'] = trip.signed_up_participants.filter(signup__on_trip=True)
        context_data['info_form'] = self.get_info_form(trip)
        return context_data


class ChairTripView(ApprovedTripsMixin, TripMedical, DetailView):
    """ Give a view of the trip intended to let chairs approve or not.

    Will show just the important details, like leaders, description, & itinerary.
    """
    template_name = 'chair/trips/view.html'

    def get_other_trips(self):
        """ Get the trips that come before and after this trip. """
        this_trip = self.get_object()

        ordered_trips = iter(self.get_queryset().filter(chair_approved=False))
        prev_trip = None
        for trip in ordered_trips:
            if trip.pk == this_trip.pk:
                try:
                    next_trip = next(ordered_trips)
                except StopIteration:
                    next_trip = None
                break
            prev_trip = trip
        else:
            return None, None  # (Could be the last unapproved trip)
        return prev_trip, next_trip

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['prev_trip'], context['next_trip'] = self.get_other_trips()
        context['info_form'] = self.get_info_form(context['trip'])
        return context

    def post(self, request, *args, **kwargs):
        """ Mark the trip approved and move to the next one. """
        trip = self.get_object()
        prev_trip, next_trip = self.get_other_trips()  # Do this before saving trip
        trip.chair_approved = True
        trip.save()
        if next_trip:
            return redirect(reverse('view_trip_for_approval', args=(self.activity, next_trip.id,)))
        else:
            return redirect(reverse('manage_trips', args=(self.activity,)))

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        if not perm_utils.is_chair(request.user, trip.activity):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class TripItineraryView(UpdateView, TripLeadersOnlyView, ItineraryInfoFormMixin):
    """ A hybrid view for creating/editing trip info for a given trip. """
    model = models.Trip
    context_object_name = 'trip'
    template_name = 'trips/itinerary.html'
    form_class = forms.TripInfoForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['itinerary_available_at'] = itinerary_available_at(self.trip.trip_date)
        context['info_form_available'] = local_now() >= context['itinerary_available_at']
        return context

    def get_initial(self):
        self.trip = self.object  # Form instance will become object
        return {'trip': self.trip}

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['instance'] = self.trip.info
        return kwargs

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        signups = self.trip.signup_set.filter(on_trip=True)
        on_trip = (Q(pk__in=self.trip.leaders.all()) |
                   Q(signup__in=signups))
        participants = models.Participant.objects.filter(on_trip).distinct()
        has_car_info = participants.filter(car__isnull=False)
        form.fields['drivers'].queryset = has_car_info
        return form

    def form_valid(self, form):
        if not self.info_form_available(self.trip):
            form.errors['__all__'] = ErrorList(["Form not yet available!"])
            return self.form_invalid(form)
        self.trip.info = form.save()
        self.trip.save()
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('view_trip', args=(self.trip.id,))


class StatsView(TemplateView):
    template_name = 'stats/index.html'


class RunTripLotteryView(DetailView, TripLeadersOnlyView):
    model = models.Trip

    def post(self, request, *args, **kwargs):
        trip = self.get_object()
        runner = SingleTripLotteryRunner(trip)
        runner()
        return redirect(reverse('view_trip', args=(trip.pk,)))
