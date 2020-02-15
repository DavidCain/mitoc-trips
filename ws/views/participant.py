"""
Views that interact with the Participant model.

The "Participant" is the core organization model of the trips system. Every
user who has completed the mandatory signup information is given a Participant
object that's linked to their user account.
"""
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import DeleteView, DetailView, FormView, TemplateView, View
from django.views.generic.detail import SingleObjectMixin
from kombu.exceptions import OperationalError

import ws.messages.leader
import ws.messages.lottery
import ws.messages.participant
import ws.utils.dates as date_utils
import ws.utils.perms as perm_utils
from ws import enums, forms, models, tasks, wimp
from ws.decorators import admin_only, group_required, user_info_required
from ws.mixins import LectureAttendanceMixin, LotteryPairingMixin
from ws.templatetags.trip_tags import annotated_for_trip_list
from ws.utils.models import problems_with_profile

logger = logging.getLogger(__name__)


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

    @staticmethod
    def prefix(base, **kwargs):
        return dict(prefix=base, scope_prefix=base + '_scope', **kwargs)

    def get_context_data(self, **kwargs):
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
        elif participant.affiliation_dated or not participant.info_current:
            # Nulling this out forces the user to consciously choose an accurate value
            # (Only null out the field if it's the user editing their own profile, though)
            if self.request.participant == participant:
                par_kwargs["initial"] = {'affiliation': None}

        verified_mit_emails = self.user.emailaddress_set.filter(
            verified=True, email__iendswith='mit.edu'
        )

        context = {
            # For everybody but an admin, `participant` is just `viewing_participant`
            'participant': participant,
            'medical_info_scrubbed': bool(
                participant and e_info and not e_info.allergies
            ),
            'has_mit_email': verified_mit_emails.exists(),
            'currently_has_car': bool(car),
            'participant_form': forms.ParticipantForm(post, **par_kwargs),
            'car_form': forms.CarForm(post, instance=car, **self.prefix('car')),
            'emergency_info_form': forms.EmergencyInfoForm(
                post, instance=e_info, **self.prefix('einfo')
            ),
            'emergency_contact_form': forms.EmergencyContactForm(
                post, instance=e_contact, **self.prefix('econtact')
            ),
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
        required_dict = {
            key: val
            for key, val in context.items()
            if isinstance(val, forms.NgModelForm)
        }

        if not self.has_car:
            required_dict.pop('car_form')
            context['car_form'] = forms.CarForm()  # Avoid validation errors

        if all(form.is_valid() for form in required_dict.values()):
            orig_affiliation = self.participant and self.participant.affiliation
            participant = self._save_forms(self.user, required_dict)
            updating_self = participant == self.request.participant
            if updating_self:
                messages.success(request, self.update_msg)

            # We always store current affiliation when self-editing (even if
            # unchanged in the trips db) because affiliation could have changed
            # in the gear database via waivers, membership dues, etc.
            if updating_self or participant.affiliation != orig_affiliation:
                try:
                    tasks.update_participant_affiliation.delay(participant.pk)
                except OperationalError:
                    logger.error(
                        "Unable to update affiliation to %s for participant %s",
                        participant.pk,
                        participant.affiliation,
                    )

            return self.success_redirect()

        return render(request, self.template_name, context)

    @transaction.atomic
    def _save_forms(self, user, post_forms):
        """ Given completed, validated forms, handle saving all.

        If no CarForm is supplied, a participant's existing car will be removed.

        Returns the saved Participant object.

        :param post_forms: Dictionary of <template_name>: <form>
        """
        participant = post_forms['participant_form'].save(commit=False)
        if participant.pk:  # Existing participant! Lock for UPDATE now.
            # (we don't also lock other objects via JOIN since those can be NULL)
            models.Participant.objects.filter(pk=participant.pk).select_for_update()

        e_contact = post_forms['emergency_contact_form'].save()
        e_info = post_forms['emergency_info_form'].save(commit=False)
        e_info.emergency_contact = e_contact
        e_info = post_forms['emergency_info_form'].save()

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

        if participant == self.request.participant:
            participant.profile_last_updated = date_utils.local_now()
        participant.save()
        if del_car:
            car.delete()
        return participant

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

    def get(self, request, *args, **kwargs):
        for problem in problems_with_profile(request.participant):
            messages.info(request, problem.how_to_fix, extra_tags='safe')
        return super().get(request, *args, **kwargs)


class ParticipantLookupView(TemplateView, FormView):
    template_name = 'participants/view.html'
    form_class = forms.ParticipantLookupForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['user_viewing'] = False
        context['lookup_form'] = self.get_form(self.form_class)
        return context

    def form_valid(self, form):
        participant = form.cleaned_data['participant']
        return redirect(reverse('view_participant', args=(participant.id,)))

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ParticipantView(
    ParticipantLookupView,
    SingleObjectMixin,
    LotteryPairingMixin,
    LectureAttendanceMixin,
):
    model = models.Participant
    context_object_name = 'participant'

    def get_queryset(self):
        """ Select related fields that will be displayed on the page. """
        par = super().get_queryset()
        return par.select_related(
            'emergency_info__emergency_contact', 'car', 'lotteryinfo'
        )

    def get_trips(self):
        participant = self.object or self.get_object()

        today = date_utils.local_date()

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
        trips_created = models.Trip.objects.filter(
            creator=participant
        ).prefetch_related(*prefetches)

        # Avoid doubly-listing trips where they participated or led the trip
        created_but_not_on = trips_created.exclude(leading_trip | par_on_trip)

        return {
            'current': {
                'on_trip': accepted.filter(in_future),
                'waitlisted': waitlisted.filter(in_future),
                'leader': trips_led.filter(in_future),
                'creator': created_but_not_on.filter(in_future),
                'wimp': participant.wimp_trips.filter(in_future),
            },
            'past': {
                'on_trip': accepted.filter(in_past),
                'leader': trips_led.filter(in_past),
                'creator': created_but_not_on.filter(in_past),
                'wimp': participant.wimp_trips.filter(in_past),
            },
        }

    @staticmethod
    def get_stats(trips):
        if not any(trips['past'].values()):
            return []

        def count(key):
            num = len(trips['past'][key])
            plural = '' if num == 1 else 's'
            return f"{num} trip{plural}"

        # Stats that are always reported for leaders
        stats = [f"Attended {count('on_trip')}", f"Led {count('leader')}"]

        # Optional stats
        if trips['past']['wimp']:
            stats.append(f"WIMPed {count('wimp')}")
        if trips['past']['creator']:
            stats.append(f"Created (but wasn't on) {count('creator')}")

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
        context['show_attendance'] = date_utils.is_currently_iap() and (
            date_utils.ws_lectures_complete() or can_set_attendance
        )
        if can_set_attendance:
            context['attended_lectures'] = models.LectureAttendance.objects.filter(
                participant=participant, year=date_utils.ws_year()
            ).exists()

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
        context['emergency_contact_form'] = forms.EmergencyContactForm(
            instance=e_contact
        )
        context['participant'] = participant
        if not user_viewing:
            feedback = participant.feedback_set.select_related('trip', 'leader')
            feedback = feedback.prefetch_related('leader__leaderrating_set')
            context['all_feedback'] = feedback
        context['ratings'] = participant.ratings(must_be_active=True)

        if participant.car:
            context['car_form'] = forms.CarForm(instance=participant.car)
        context['wimp'] = self.wimp
        return context

    @property
    def wimp(self):
        """ Return the current WIMP, if there is one & it's appropriate to display them. """
        participant = self.object

        # Regardless of time of year, or any upcoming WS trips, admins always see WIMP
        if self.request.user.is_superuser:
            return wimp.current_wimp()

        # If there aren't any upcoming trips (or trips today), don't show WIMP
        # This will ensure that we hide the WIMP when:
        # - It's not Winter School
        # - Winter School just ended, but `is_currently_iap()` can't tell
        # - The weekend just ended, and we don't yet have a new WIMP
        ws_trips = models.Trip.objects.filter(
            program=enums.Program.WINTER_SCHOOL.value,
            trip_date__gte=date_utils.local_date(),
        )
        if not ws_trips:
            return None

        # Participants don't need to know the WIMP, only leaders/chairs do
        if not (
            participant.can_lead(enums.Program.WINTER_SCHOOL)
            or perm_utils.is_chair(self.request.user, enums.Activity.WINTER_SCHOOL)
        ):
            return None

        return wimp.current_wimp()

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class ParticipantDetailView(ParticipantView, FormView, DetailView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        args = self.request.GET
        show_feedback = args.get('show_feedback', '0') not in {'0', ''}
        if show_feedback:
            logger.info(
                "%s (#%d) viewed feedback for %s (#%d)",
                self.request.participant,
                self.request.participant.pk,
                self.participant,
                self.participant.pk,
            )
        context['hide_comments'] = not show_feedback
        context['display_log_notice'] = show_feedback
        return context

    def dispatch(self, request, *args, **kwargs):
        if request.participant == self.get_object():
            return redirect(reverse('home'))
        return super().dispatch(request, *args, **kwargs)


class ProfileView(ParticipantView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        args = self.request.GET
        context['just_signed'] = args.get('event') == 'signing_complete'
        return context

    @staticmethod
    def render_landing_page(request):
        today = date_utils.local_date()
        ordered_trips = models.Trip.objects.order_by('-trip_date', '-time_created')
        current_trips = ordered_trips.filter(trip_date__gte=today)
        context = {'current_trips': annotated_for_trip_list(current_trips)}

        num_trips = len(context['current_trips'])  # Use len to avoid extra query

        # If we don't have many upcoming trips, show some recent ones
        if num_trips < 8:
            extra_trips = max(2, 8 - num_trips)
            recent_trips = ordered_trips.filter(trip_date__lt=today)[:extra_trips]
            context['recent_trips'] = annotated_for_trip_list(recent_trips)

        return render(request, 'home.html', context)

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.render_landing_page(request)
        if not request.participant:
            return redirect(reverse('edit_profile'))

        # We _really_ want accurate information on affiliation.
        # Immediately redirect people so we can get updated affiliation
        if request.participant.affiliation_dated:
            return redirect(reverse('edit_profile'))

        ws.messages.leader.Messages(request).supply()
        ws.messages.participant.Messages(request).supply()
        ws.messages.lottery.Messages(request).supply()

        return super().get(request, *args, **kwargs)

    def get_object(self, queryset=None):
        self.kwargs['pk'] = self.request.participant.id
        return super().get_object(queryset)

    # Login is not required - we'll handle that in `get()`
    def dispatch(self, request, *args, **kwargs):
        return View.dispatch(self, request, *args, **kwargs)
