"""
Views that interact with the Participant model.

The "Participant" is the core organization model of the trips system. Every
user who has completed the mandatory signup information is given a Participant
object that's linked to their user account.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic.detail import SingleObjectMixin
from django.views.generic import (DeleteView, DetailView, FormView,
                                  TemplateView, View)

from ws import forms
from ws import message_generators
from ws import models
from ws import tasks
from ws.decorators import admin_only, group_required, user_info_required
from ws.mixins import LotteryPairingMixin, LectureAttendanceMixin
from ws.templatetags.trip_tags import annotated_for_trip_list
from ws.utils.dates import local_date, local_now, is_winter_school, ws_year
from ws.utils.model_dates import ws_lectures_complete
import ws.utils.perms as perm_utils


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

        context = {
            'currently_has_car': bool(car),
            'participant_form': forms.ParticipantForm(post, **par_kwargs),
            'car_form': forms.CarForm(post, instance=car, **self.prefix('car')),
            'emergency_info_form': forms.EmergencyInfoForm(post, instance=e_info,
                                                           **self.prefix('einfo')),
            'emergency_contact_form': forms.EmergencyContactForm(post, instance=e_contact,
                                                                 **self.prefix('econtact')),
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
            orig_affiliation = self.participant and self.participant.affiliation
            participant = self._save_forms(self.user, required_dict)
            updating_self = participant == self.request.participant
            if updating_self:
                messages.success(request, self.update_msg)

            # We always store current affiliation when self-editing (even if
            # unchanged in the trips db) because affiliation could have changed
            # in the gear database via waivers, membership dues, etc.
            if updating_self or participant.affiliation != orig_affiliation:
                tasks.update_participant_affiliation.delay(participant.pk)
            return self.success_redirect()
        else:
            return render(request, self.template_name, context)

    def _save_forms(self, user, post_forms):
        """ Given completed, validated forms, handle saving all.

        If no CarForm is supplied, a participant's existing car will be removed.

        Returns the saved Participant object.

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

        if participant == self.request.participant:
            participant.profile_last_updated = local_now()
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
        par = request.participant
        safe_messages = par.problems_with_profile if par else []
        for msg in safe_messages:
            messages.info(request, msg, extra_tags='safe')
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


class ParticipantView(ParticipantLookupView, SingleObjectMixin,
                      LotteryPairingMixin, LectureAttendanceMixin):
    model = models.Participant
    context_object_name = 'participant'

    def get_queryset(self):
        """ Select related fields that will be displayed on the page. """
        par = super().get_queryset()
        return par.select_related('emergency_info__emergency_contact',
                                  'car', 'lotteryinfo')

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
                'wimp': participant.wimp_trips.filter(in_future),
            },
            'past': {
                'on_trip': accepted.filter(in_past),
                'leader': trips_led.filter(in_past),
                'creator': created_but_not_on.filter(in_past),
                'wimp': participant.wimp_trips.filter(in_past),
            },
        }

    def get_stats(self, trips):
        if not any(trips['past'].values()):
            return []

        def count(key):
            num = len(trips['past'][key])
            plural = '' if num == 1 else 's'
            return f"{num} trip{plural}"

        # Stats that are always reported for leaders
        stats = [
            f"Attended {count('on_trip')}",
            f"Led {count('leader')}",
        ]

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
        context['show_attendance'] = (
            is_winter_school() and (ws_lectures_complete() or can_set_attendance)
        )
        if can_set_attendance:
            context['attended_lectures'] = models.LectureAttendance.objects.filter(
                participant=participant,
                year=ws_year()
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
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        args = self.request.GET
        context['just_signed'] = args.get('event') == 'signing_complete'
        return context

    def render_landing_page(self, request):
        today = local_date()
        current_trips = models.Trip.objects.filter(trip_date__gte=today)
        context = {'current_trips': annotated_for_trip_list(current_trips)}

        num_trips = len(context['current_trips'])  # Use len to avoid extra query

        # If we don't have many upcoming trips, show some recent ones
        if num_trips < 8:
            extra_trips = max(2, 8 - num_trips)
            recent_trips = models.Trip.objects.filter(trip_date__lt=today)[:extra_trips]
            context['recent_trips'] = annotated_for_trip_list(recent_trips)

        return render(request, 'home.html', context)

    def get(self, request, *args, **kwargs):
        if request.user.is_anonymous:
            return self.render_landing_page(request)
        if not request.participant:
            return redirect(reverse('edit_profile'))

        # We _really_ want accurate information on affiliation.
        # Immediately redirect people so we can get updated affiliation
        if request.participant.affiliation_dated:
            return redirect(reverse('edit_profile'))

        message_generators.warn_if_needs_update(request)
        message_generators.complain_if_missing_feedback(request)

        lottery_messages = message_generators.LotteryMessages(request)
        lottery_messages.supply_all_messages()
        return super().get(request, *args, **kwargs)

    def get_object(self, queryset=None):
        self.kwargs['pk'] = self.request.participant.id
        return super().get_object(queryset)

    # Login is not required - we'll handle that in `get()`
    def dispatch(self, request, *args, **kwargs):
        return View.dispatch(self, request, *args, **kwargs)
