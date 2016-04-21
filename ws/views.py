from itertools import chain
import json

from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.urlresolvers import reverse, reverse_lazy
from django.db.models import Count, Sum
from django.forms.models import modelformset_factory
from django.forms import HiddenInput
from django.forms.utils import ErrorList
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views.generic import (CreateView, DetailView, DeleteView, FormView,
                                  ListView, TemplateView, UpdateView, View)
from django.views.generic.detail import SingleObjectMixin

from allauth.account.views import PasswordChangeView

from ws import forms
from ws import models
from ws.dateutils import local_now
from ws.decorators import group_required, user_info_required, admin_only, chairs_only
from ws import dateutils
from ws import message_generators
from ws import signup_utils
from ws import perm_utils


class LeadersOnlyView(View):
    @method_decorator(group_required('leaders', *perm_utils.all_chair_groups))
    def dispatch(self, request, *args, **kwargs):
        """ Only allow creator, leaders of the trip, and chairs to edit. """
        trip = self.get_object()
        chair = perm_utils.is_chair(request.user, trip.activity)
        if not (leader_on_trip(request, trip, creator_allowed=True) or chair):
            return render(request, 'not_your_trip.html', {'trip': trip})
        return super(LeadersOnlyView, self).dispatch(request, *args, **kwargs)


class LoginAfterPasswordChangeView(PasswordChangeView):
    @property
    def success_url(self):
        return reverse_lazy('account_login')

login_after_password_change = login_required(LoginAfterPasswordChangeView.as_view())


def leader_on_trip(request, trip, creator_allowed=False):
    try:
        leader = request.user.participant
    except ObjectDoesNotExist:
        return False
    else:
        return (leader in trip.leaders.all() or
                creator_allowed and leader == trip.creator)


class UpdateParticipantView(TemplateView):
    template_name = 'update_info.html'
    update_msg = 'Personal information updated successfully'

    @property
    def has_car(self):
        return 'has_car' in self.request.POST

    @property
    def participant(self):
        try:
            return self.request.user.participant
        except ObjectDoesNotExist:
            return None

    def prefix(self, base, **kwargs):
        return dict(prefix=base, scope_prefix=base + '_scope', **kwargs)

    def get_context_data(self):
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
        if not participant:
            par_kwargs["initial"] = {'email': self.request.user.email}

        context = {
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
            self._save_forms(request.user, required_dict)
            messages.add_message(request, messages.SUCCESS, self.update_msg)
            next_url = request.GET['next'] if 'next' in request.GET else 'home'
            return redirect(next_url)
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
        participant.user = user
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
        return super(UpdateParticipantView, self).dispatch(request, *args, **kwargs)


class ParticipantView(TemplateView, SingleObjectMixin):
    model = models.Participant
    context_object_name = 'participant'
    template_name = 'participant_detail.html'

    def get_trips(self):
        participant = self.object or self.get_object()
        signups = participant.signup_set

        today = local_now().date()

        # Signups
        in_future = Q(trip__trip_date__gte=today)
        in_past = Q(trip__trip_date__lt=today)
        accepted_signups = signups.filter(on_trip=True)
        waitlisted = signups.filter(in_future, waitlistsignup__isnull=False)

        trips_led = participant.trips_led.all()

        return {'current': {
                    'on_trip': [signup.trip for signup in accepted_signups.filter(in_future)],
                    'waitlisted': [signup.trip for signup in waitlisted],
                    'leader': trips_led.filter(trip_date__gte=today),
                    },
                'past': {
                    'on_trip': [signup.trip for signup in accepted_signups.filter(in_past)],
                    'leader': trips_led.filter(trip_date__lt=today),
                    },
                }

    def get_stats(self, trips):
        num_attended = len(trips['past']['on_trip'])
        num_led = len(trips['past']['leader'])
        stats = ["Attended {} trip".format(num_attended) + ('' if num_attended == 1 else 's'),
                 "Led {} trip".format(num_led) + ('' if num_led == 1 else 's')]
        return stats

    def get_context_data(self, **kwargs):
        participant = self.object = self.get_object()
        context = super(ParticipantView, self).get_context_data(**kwargs)

        user_viewing = self.request.user.participant == participant
        context['user_viewing'] = user_viewing

        context['trips'] = trips = self.get_trips()
        context['stats'] = self.get_stats(trips)

        e_info = participant.emergency_info
        e_contact = e_info.emergency_contact
        context['emergency_info_form'] = forms.EmergencyInfoForm(instance=e_info)
        context['emergency_contact_form'] = forms.EmergencyContactForm(instance=e_contact)
        context['participant'] = participant
        if not user_viewing:
            feedback = participant.feedback_set.select_related('trip', 'leader')
            context['all_feedback'] = feedback
        context['ratings'] = participant.leaderrating_set.all()
        chair_activities = set(perm_utils.chair_activities(participant.user))
        context['chair_activities'] = [label for (activity, label) in models.LeaderRating.ACTIVITY_CHOICES
                                       if activity in chair_activities]

        if participant.car:
            context['car_form'] = forms.CarForm(instance=participant.car)
        return context

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ParticipantView, self).dispatch(request, *args, **kwargs)


class ParticipantDetailView(ParticipantView, DetailView):
    def get_queryset(self):
        participant = super(ParticipantDetailView, self).get_queryset()
        return participant.select_related('emergency_info__emergency_contact')

    def get(self, request, *args, **kwargs):
        if request.user.participant == self.get_object():
            return redirect(reverse('profile'))
        return super(ParticipantDetailView, self).get(request, *args, **kwargs)

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super(ParticipantView, self).dispatch(request, *args, **kwargs)


class ProfileView(ParticipantView):
    def get(self, request, *args, **kwargs):
        message_generators.warn_if_needs_update(request)
        message_generators.complain_if_missing_feedback(request)

        lottery_messages = message_generators.LotteryMessages(request)
        lottery_messages.supply_all_messages()
        return super(ProfileView, self).get(request, *args, **kwargs)

    def get_object(self):
        return self.request.user.participant


class SignUpView(CreateView):
    """ Special view designed to be accessed only on invalid signup form

    The "select trip" field is hidden, as this page is meant to be accessed
    only from a Trip-viewing page. Technically, by manipulating POST data on
    the hidden field (Trip), participants could sign up for any trip this way.
    This is not really an issue, though, so no security flaw.
    """
    model = models.SignUp
    form_class = forms.SignUpForm
    template_name = 'trip_signup.html'

    def get_form(self, form_class):
        signup_form = super(SignUpView, self).get_form(form_class)
        signup_form.fields['trip'].widget = HiddenInput()
        return signup_form

    def form_valid(self, form):
        """ After is_valid() and some checks, assign participant from User.

        If the participant has signed up before, halt saving, and return
        a form with errors (this shouldn't happen, as a template should
        prevent the form from being displayed in the first place).
        """
        signup = form.save(commit=False)
        signup.participant = self.request.user.participant
        if signup.trip in signup.participant.trip_set.all():
            form.errors['__all__'] = ErrorList(["Already signed up!"])
            return self.form_invalid(form)
        elif not signup.trip.signups_open:  # Guards against direct POST
            form.errors['__all__'] = ErrorList(["Signups aren't open!"])
            return self.form_invalid(form)
        return super(SignUpView, self).form_valid(form)

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, "Signed up!")
        return reverse('view_trip', args=(self.object.trip.id,))

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(SignUpView, self).dispatch(request, *args, **kwargs)


class TripDetailView(DetailView):
    model = models.Trip
    context_object_name = 'trip'

    def get_queryset(self):
        trips = super(TripDetailView, self).get_queryset()
        return trips.select_related('info')

    def get_signups(self):
        """ Signups, with related fields used in templates preselected. """
        signups = models.SignUp.objects.filter(trip=self.object)
        signups = signups.select_related('participant', 'trip')
        return signups.select_related('participant__lotteryinfo')

    def get_leaders(self):
        leaders = self.object.leaders.all()
        return leaders.select_related('lotteryinfo')

    @property
    def wl_signups(self):
        trip = self.object
        return trip.waitlist.signups.select_related('participant',
                                                    'participant__lotteryinfo')

    def get_context_data(self, **kwargs):
        """ Create form for signup (only if signups open). """
        context = super(TripDetailView, self).get_context_data()
        context['leaders'] = self.get_leaders()
        context['signups'] = self.get_signups()
        context['waitlist_signups'] = self.wl_signups
        return context


class TripView(TripDetailView):
    template_name = 'view_trip.html'

    def get_participant_signup(self, trip=None):
        """ Return viewer's signup for this trip (if one exists, else None) """
        try:
            participant = self.request.user.participant
        except ObjectDoesNotExist:  # Logged in, no participant info
            return None
        trip = trip or self.get_object()
        return participant.signup_set.filter(trip=trip).first()

    def get_context_data(self, **kwargs):
        """ Create form for signup (only if signups open). """
        context = super(TripView, self).get_context_data()
        signups = context['signups']
        trip = self.object
        context['is_chair'] = perm_utils.is_chair(self.request.user, trip.activity)
        if trip.signups_open:
            signup_form = forms.SignUpForm(initial={'trip': trip})
            signup_form.fields['trip'].widget = HiddenInput()
            context['signup_form'] = signup_form
        context['participant_signup'] = self.get_participant_signup(trip)
        context['has_notes'] = trip.notes or any(s.notes for s in signups)
        context['signups_on_trip'] = signups.filter(on_trip=True)
        return context

    def get(self, request, *args, **kwargs):
        trip = self.get_object()
        if leader_on_trip(request, trip):
            return redirect(reverse('admin_trip', args=(trip.id,)))
        return super(TripView, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """ Add signup to trip or waitlist, if applicable.

        Used if the participant has signed up, but wasn't placed.
        """
        signup = self.get_participant_signup()
        signup_utils.trip_or_wait(signup, self.request, trip_must_be_open=True)
        return self.get(request)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripView, self).dispatch(request, *args, **kwargs)


class TripInfoEditable(object):
    def friday_before(self, trip):
        return dateutils.friday_before(trip.trip_date)

    def info_form_available(self, trip):
        """ Trip itinerary should only be submitted Friday before or later. """
        today = local_now().date()
        return today >= self.friday_before(trip)

    def info_form_context(self, trip):
        return {'info_form_available': self.info_form_available(trip),
                'friday_before': self.friday_before(trip)}

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


class AdminTripSignupsView(SingleObjectMixin, LeadersOnlyView, TripInfoEditable):
    model = models.Trip

    # TODO: Select related fields
    #def get_queryset(self):

    def post(self, request, *args, **kwargs):
        trip = self.object = self.get_object()
        bad_request = JsonResponse({'message': 'Bad request'}, status=400)

        postdata = json.loads(self.request.body)
        signups = postdata.get('signups', [])
        maximum_participants = postdata.get('maximum_participants')
        try:
            signups = list(self.to_objects(signups))
        except (KeyError, ObjectDoesNotExist):
            return bad_request

        # Any non-validation errors will trigger rollback
        with transaction.atomic():
            try:
                self.update(trip, signups, maximum_participants)
            except ValidationError:
                return bad_request
            else:
                return JsonResponse({})

    def update(self, trip, signups, maximum_participants):
        """ Take parsed input data and apply the changes. """
        if maximum_participants:
            trip.maximum_participants = maximum_participants
            trip.full_clean()  # Raises ValidationError
            trip.save()
        self.update_signups(signups, trip)  # Anything already on should be waitlisted

    def update_signups(self, signups, trip):
        """ Mark all signups as not on trip, then add signups in order. """
        for signup, remove in signups:
            signup.on_trip = False
            signup.skip_signals = True  # Skip the waitlist-bumping behavior
            signup.save()

        for order, (signup, remove) in enumerate(signups):
            if remove:
                signup.delete()
            else:
                signup_utils.trip_or_wait(signup, trip_must_be_open=False)
                signup_utils.next_in_order(signup, order)


    def to_objects(self, signups):
        """ Convert POSTed JSON to an array of its corresponding objects. """
        for signup_dict in signups:
            remove = bool(signup_dict.get('deleted'))
            if signup_dict['id']:
                signup = models.SignUp.objects.get(pk=signup_dict['id'])
            elif remove:
                continue  # No point creating signup, only to remove later
            else:
                par_id = signup['participant']['id']
                par = models.Participant.objects.get(pk=par_id)
                signup = models.SignUp(participant=par, trip=self.object)
            yield signup, remove

    def describe_signup(self, signup):
        """ Yield everything used in the participant-selecting modal."""
        par = signup.participant

        try:
            lotteryinfo = par.lotteryinfo
        except:
            car_status = num_passengers = None
        else:
            car_status = lotteryinfo.car_status
            num_passengers = lotteryinfo.number_of_passengers

        return {'id': signup.id,
                'participant': {'id': par.id,
                                'name': par.name,
                                'email': par.email},
                'feedback': [{'showed_up': f.showed_up,
                              'leader': f.leader.name,
                              'comments': f.comments,
                              'trip': {'id': f.trip.id, 'name': f.trip.name},
                              } for f in par.feedback_set.all()],
                'also_on': [{'id': s.trip.id, 'name': s.trip.name}
                            for s in signup.other_signups],
                'car_status': car_status,
                'number_of_passengers': num_passengers,
                'notes': signup.notes}

    def get(self, request, *args, **kwargs):
        """ Get information about a trip's signups. """
        trip = self.get_object()
        signups = trip.signup_set.filter(on_trip=True)

        ret = [self.describe_signup(signup)
               for signup in chain(signups, trip.waitlist.signups)]

        return JsonResponse({'signups': ret})


class AdminTripView(TripDetailView, LeadersOnlyView, TripInfoEditable):
    template_name = 'admin_trip.html'
    par_prefix = "ontrip"
    wl_prefix = "waitlist"

    def get_context_data(self, **kwargs):
        trip = self.object = self.get_object()
        context = super(AdminTripView, self).get_context_data()
        context.update(self.info_form_context(trip))
        return context


class ReviewTripView(DetailView):
    queryset = models.Trip.objects.all()
    context_object_name = 'trip'
    template_name = 'review_trip.html'
    success_msg = "Thanks for your feedback"
    flake_msg = "Feel free to elaborate on why flaking participants didn't show"

    @property
    def feedback_formset(self):
        return modelformset_factory(models.Feedback, extra=0)

    def create_flake_feedback(self, trip, leader, participants):
        flaky = {'showed_up': False, 'comments': " ",
                 'leader': leader, 'trip': trip}
        for participant in participants:
            if not models.Feedback.objects.filter(leader=leader, trip=trip,
                                                  participant=participant):
                models.Feedback.objects.create(participant=participant, **flaky)

    def post(self, request, *args, **kwargs):
        trip = self.object = self.get_object()
        flake_form = self.flake_form
        feedback_list = self.feedback_list

        if (all(form.is_valid() for participant, form in feedback_list) and
                flake_form.is_valid()):
            leader = request.user.participant

            for participant, form in feedback_list:
                feedback = form.save(commit=False)
                feedback.leader = leader
                feedback.participant = participant
                feedback.trip = trip
                form.save()

            flake_participants = flake_form.cleaned_data['flakers']
            self.create_flake_feedback(trip, leader, flake_participants)

            messages.add_message(request, messages.SUCCESS, self.success_msg)
            if flake_participants:
                messages.add_message(request, messages.SUCCESS, self.flake_msg)
                return redirect(reverse('review_trip', args=(trip.id,)))
            else:
                return redirect(reverse('home'))
        return self.get(request, *args, **kwargs)

    @property
    def trip_participants(self):
        accepted_signups = self.object.signup_set.filter(on_trip=True)
        accepted_signups = accepted_signups.select_related('participant')
        return [signup.participant for signup in accepted_signups]

    def get_existing_feedback(self, participant, leader):
        trip = self.object
        feedback = models.Feedback.objects.filter(participant=participant,
                                                  trip=trip, leader=leader)
        return feedback.first() or None

    @property
    def flake_form(self):
        post = self.request.POST if self.request.method == 'POST' else None
        return forms.FlakeForm(self.object, post)

    def all_flake_feedback(self, leader):
        trip = self.object
        feedback = models.Feedback.objects.filter(trip=trip, leader=leader)
        return feedback.exclude(participant__in=self.trip_participants)

    @property
    def feedback_list(self):
        post = self.request.POST if self.request.method == 'POST' else None
        leader = self.request.user.participant
        feedback_list = []

        for participant in self.trip_participants:
            instance = self.get_existing_feedback(participant, leader)
            initial = {'participant': participant}
            form = forms.FeedbackForm(post, instance=instance, initial=initial,
                                      prefix=participant.id)
            feedback_list.append((participant, form))

        for feedback in self.all_flake_feedback(leader):
            form = forms.FeedbackForm(post, instance=feedback, initial=initial,
                                      prefix=feedback.participant.id)
            feedback_list.append((feedback.participant, form))
        return feedback_list

    def get_context_data(self, **kwargs):
        today = local_now().date()
        trip = self.object = self.get_object()
        return {"trip": trip, "trip_completed": today >= trip.trip_date,
                "feedback_list": self.feedback_list,
                "flake_form": self.flake_form}

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        if not leader_on_trip(request, trip):
            return render(request, 'not_your_trip.html', {'trip': trip})
        return super(ReviewTripView, self).dispatch(request, *args, **kwargs)


def home(request):
    message_generators.warn_if_needs_update(request)
    message_generators.complain_if_missing_feedback(request)

    lottery_messages = message_generators.LotteryMessages(request)
    lottery_messages.supply_all_messages()
    return render(request, 'home.html')


class LeaderView(ListView):
    model = models.Participant
    context_object_name = 'leaders'
    template_name = 'leaders.html'

    def get_queryset(self):
        return models.Participant.leaders.get_queryset()

    def get_context_data(self, **kwargs):
        context_data = super(LeaderView, self).get_context_data(**kwargs)

        closed_activities = models.LeaderRating.CLOSED_ACTIVITY_CHOICES
        activities = [(val, label) for (val, label) in closed_activities
                      if val != 'cabin']
        context_data['activities'] = activities
        return context_data

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super(LeaderView, self).dispatch(request, *args, **kwargs)


class JsonLeaderView(LeaderView):
    def render_to_response(self, context, **response_kwargs):
        leaders = self.get_queryset()
        activity = self.kwargs['activity']
        if activity:
            leaders = leaders.filter(leaderrating__activity=activity).distinct()
        ret = [{'name': leader.name, 'id': leader.id,
                'ratings': list(leader.leaderrating_set.values("activity",
                                                               "rating"))}
               for leader in leaders]

        return JsonResponse({'leaders': ret})


class BecomeLeaderView(CreateView):
    template_name = "become_leader.html"
    model = models.LeaderApplication
    form_class = forms.LeaderApplicationForm

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(BecomeLeaderView, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """ Link the application to the submitting participant. """
        application = form.save(commit=False)
        application.participant = self.request.user.participant
        received = "Leader application received!"
        messages.add_message(self.request, messages.SUCCESS, received)
        return super(BecomeLeaderView, self).form_valid(form)

    def get_context_data(self, **kwargs):
        """ Give next year's value in the context. """
        context_data = super(BecomeLeaderView, self).get_context_data(**kwargs)
        context_data['year'] = local_now().date().year + 1
        return context_data

    def get_success_url(self):
        return reverse('home')


class AllLeaderApplicationsView(ListView):
    model = models.LeaderApplication
    context_object_name = 'leader_applications'
    template_name = 'manage_applications.html'

    def get_queryset(self):
        applications = super(AllLeaderApplicationsView, self).get_queryset()
        return applications.select_related('participant')

    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(AllLeaderApplicationsView, self).dispatch(request, *args, **kwargs)


class LeaderApplicationView(DetailView):
    model = models.LeaderApplication
    context_object_name = 'application'
    template_name = 'view_application.html'

    def existing_rating(self, activity, participant):
        find_rating = Q(participant__pk=participant.pk, activity=activity)
        return models.LeaderRating.objects.filter(find_rating).first()

    def pre_fill_form(self, kwargs, activity, participant):
        kwargs['initial']['activity'] = activity
        existing = self.existing_rating(activity, participant)
        if existing:
            kwargs['initial']['notes'] = existing.notes

    def get_context_data(self, **kwargs):
        """ Add on a form to assign/modify leader permissions. """
        context_data = super(LeaderApplicationView, self).get_context_data(**kwargs)
        application = self.get_object()
        kwargs = {'initial': {'participant': application.participant}}
        chair_activities = perm_utils.chair_activities(self.request.user)
        if chair_activities:
            kwargs['allowed_activities'] = chair_activities
            if len(chair_activities) == 1:
                self.pre_fill_form(kwargs, chair_activities[0], application.participant)

        leader_form = forms.LeaderForm(**kwargs)
        # TODO: Ensure only one leader rating exists per activity type
        leader_form.fields['participant'].widget = HiddenInput()
        context_data['leader_form'] = leader_form
        return context_data

    def post(self, request, *args, **kwargs):
        """ Save a rating for the leader. """
        leader_form = forms.LeaderForm(request.POST)

        if leader_form.is_valid():
            activity, participant = (leader_form.cleaned_data['activity'],
                                     leader_form.cleaned_data['participant'])
            existing = self.existing_rating(activity, participant)
            leader_form = forms.LeaderForm(request.POST, instance=existing)
            leader_form.save()
            leader = leader_form.instance
            update_msg = "{} given {} rating".format(leader.participant.name,
                                                     leader.rating)
            messages.add_message(request, messages.SUCCESS, update_msg)
            return redirect(reverse('manage_applications'))
        else:  # Any miscellaneous error form could possibly produce
            return render(request, 'add_leader.html', {'leader_form': leader_form})

    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(LeaderApplicationView, self).dispatch(request, *args, **kwargs)


@login_required
def get_rating(request, pk, activity):
    query = Q(participant__pk=pk, activity=activity)
    lr = models.LeaderRating.objects.filter(query).first()
    resp = {'rating': lr.rating, 'notes': lr.notes} if lr else {}
    return JsonResponse(resp)


# TODO: Convert to CreateView
@chairs_only()
def add_leader(request):
    """ Create a leader rating for an existing Participant. """
    sudo_ok = True
    if request.method == "POST":
        form = forms.LeaderForm(request.POST)
        if form.is_valid():
            activity = form.cleaned_data['activity']
            participant = form.cleaned_data['participant']
            find_rating = Q(participant__pk=participant.pk, activity=activity)
            existing = models.LeaderRating.objects.filter(find_rating).first()
            if existing:
                form = forms.LeaderForm(request.POST, instance=existing)
            if not perm_utils.is_chair(request.user, activity, sudo_ok):
                not_chair = "You cannot assign {} ratings".format(activity)
                form.add_error("activity", not_chair)
            else:
                form.save()
                messages.add_message(request, messages.SUCCESS, 'Added rating')
    else:
        # Regardless of success, empty form for quick addition of another
        allowed_activities = perm_utils.chair_activities(request.user, sudo_ok)
        kwargs = {'allowed_activities': allowed_activities}
        if len(allowed_activities) == 1:
            kwargs['initial'] = {'activity': allowed_activities[0]}
        form = forms.LeaderForm(**kwargs)
    return render(request, 'add_leader.html', {'leader_form': form})


def _manage_trips(request, TripFormSet):
    if request.method == 'POST':
        formset = TripFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated trips')
            formset = TripFormSet()
    else:
        all_trips = models.Trip.objects.all()
        all_trips = all_trips
        formset = TripFormSet(queryset=all_trips)
    return render(request, 'manage_trips.html', {'formset': formset})


@group_required('WSC')
def manage_trips(request):
    TripFormSet = modelformset_factory(models.Trip, can_delete=False, extra=0,
                                       fields=('wsc_approved',))
    return _manage_trips(request, TripFormSet)


@admin_only
def admin_manage_trips(request):
    TripFormSet = modelformset_factory(models.Trip, can_delete=True, extra=0,
                                       fields=('wsc_approved',))
    return _manage_trips(request, TripFormSet)


class AddTripView(CreateView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = 'add_trip.html'

    @property
    def participant(self):
        return self.request.user.participant

    def get_form_kwargs(self):
        kwargs = super(AddTripView, self).get_form_kwargs()
        kwargs['allowed_activities'] = self.participant.allowed_activities
        return kwargs

    def get_success_url(self):
        return reverse('view_trip', args=(self.object.id,))

    def get_initial(self):
        """ Default with trip creator among leaders. """
        initial = super(AddTripView, self).get_initial().copy()
        # It's possible for WSC to create trips while not being a leader
        if self.participant.is_leader:
            initial['leaders'] = [self.participant]
        return initial

    def form_valid(self, form):
        """ After is_valid(), assign creator from User, add empty waitlist. """
        creator = self.participant
        trip = form.save(commit=False)
        trip.creator = creator
        return super(AddTripView, self).form_valid(form)

    @method_decorator(group_required('WSC', 'leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super(AddTripView, self).dispatch(request, *args, **kwargs)


class DeleteTripView(DeleteView, LeadersOnlyView):
    model = models.Trip
    success_url = reverse_lazy('view_leader_trips')


class EditTripView(UpdateView, LeadersOnlyView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = 'edit_trip.html'

    def get_success_url(self):
        return reverse('view_trip', args=(self.object.id,))

    def _ignore_leaders_if_unchanged(self, form):
        """ Don't update the leaders m2m field if unchanged.

        This is a hack to avoid updating the m2m set (normally cleared, then
        reset) Without this, post_add (signal used to send emails) will send
        out a message to all leaders on _every_ trip update.

        A compromise: Only send emails when the leader list is changed.
        See ticket 6707 for an eventual fix to this behavior
        """
        old_pks = set(leader.pk for leader in self.object.leaders.all())
        new_pks = set(leader.pk for leader in form.cleaned_data['leaders'])
        if not old_pks.symmetric_difference(new_pks):
            form.cleaned_data.pop('leaders')

    def form_valid(self, form):
        self._ignore_leaders_if_unchanged(form)

        trip = form.save(commit=False)
        if not perm_utils.is_chair(self.request.user, trip.activity):
            trip.wsc_approved = False
        return super(EditTripView, self).form_valid(form)


class TripListView(ListView):
    """ Superclass for any view that displays a list of trips. """
    model = models.Trip
    template_name = 'view_trips.html'
    context_object_name = 'trip_queryset'
    form_class = forms.SummaryTripForm

    def get_queryset(self):
        # Each trip will need information about its leaders, so prefetch models
        trips = super(TripListView, self).get_queryset()
        trips = trips.prefetch_related('leaders')
        trips = trips.annotate(num_signups=Count('signup'))
        trips = trips
        return trips.annotate(signups_on_trip=Sum('signup__on_trip'))

    def get_context_data(self, **kwargs):
        """ Sort trips into past and present trips. """
        context_data = super(TripListView, self).get_context_data(**kwargs)
        trips = context_data[self.context_object_name]

        today = local_now().date()
        context_data['current_trips'] = trips.filter(trip_date__gte=today)
        context_data['past_trips'] = trips.filter(trip_date__lt=today)
        return context_data


class CurrentTripListView(TripListView):
    """ Superclass for any view that displays only current/upcoming trips. """
    context_object_name = 'current_trips'

    def get_queryset(self):
        queryset = super(CurrentTripListView, self).get_queryset()
        return queryset.filter(trip_date__gte=local_now().date())

    def get_context_data(self, **kwargs):
        # No point sorting into current, past (queryset already handles)
        return super(TripListView, self).get_context_data(**kwargs)


class CurrentTripsView(CurrentTripListView):
    """ View current trips. """
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class AllTripsView(TripListView):
    """ View all trips, past and present. """
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class ParticipantTripsView(TripListView):
    """ View trips the user is a participant on. """
    template_name = 'view_my_trips.html'

    def get_queryset(self):
        participant = self.request.user.participant
        accepted_signups = participant.signup_set.filter(on_trip=True)

        trips = super(ParticipantTripsView, self).get_queryset()
        return trips.filter(signup__in=accepted_signups)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class WaitlistTripsView(TripListView):
    """ View trips the user is currently waitlisted on. """
    def get_queryset(self):
        signups = self.request.user.participant.signup_set
        waitlisted_signups = signups.filter(waitlistsignup__isnull=False)

        trips = super(WaitlistTripsView, self).get_queryset()
        return trips.filter(signup__in=waitlisted_signups)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class LeaderTripsView(TripListView):
    """ View trips the user is leading. """
    def get(self, request, *args, **kwargs):
        self.queryset = request.user.participant.trips_led.all()
        return super(LeaderTripsView, self).get(request, *args, **kwargs)

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super(LeaderTripsView, self).dispatch(request, *args, **kwargs)


class LotteryPairView(CreateView):
    model = models.LotteryInfo
    template_name = 'lottery_pair.html'
    form_class = forms.LotteryPairForm
    success_url = reverse_lazy('trip_preferences')

    def get_context_data(self, **kwargs):
        """ Get a list of all other participants who've requested pairing. """
        context = super(LotteryPairView, self).get_context_data(**kwargs)
        requested = Q(lotteryinfo__paired_with=self.request.user.participant)
        context['pair_requests'] = models.Participant.objects.filter(requested)
        return context

    def get_form_kwargs(self):
        """ Edit existing instance, prevent user from pairing with self. """
        kwargs = super(LotteryPairView, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        try:
            kwargs['instance'] = self.request.user.participant.lotteryinfo
        except ObjectDoesNotExist:
            pass
        return kwargs

    def form_valid(self, form):
        participant = self.request.user.participant
        lottery_info = form.save(commit=False)
        lottery_info.participant = participant
        paired_par = form.instance.paired_with
        if not paired_par:
            no_pair_msg = "Requested normal behavior (no pairing) in lottery"
            messages.add_message(self.request, messages.SUCCESS, no_pair_msg)
        else:
            self.add_pairing_messages(paired_par)
        return super(LotteryPairView, self).form_valid(form)

    def add_pairing_messages(self, paired_par):
        """ Add messages that explain next steps for lottery pairing. """
        participant = self.request.user.participant
        try:
            reciprocal = paired_par.lotteryinfo.paired_with == participant
        except ObjectDoesNotExist:  # No lottery info for paired participant
            reciprocal = False

        pre = "Successfully paired" if reciprocal else "Requested pairing"
        paired_msg = pre + " with {}".format(paired_par)
        messages.add_message(self.request, messages.SUCCESS, paired_msg)

        if reciprocal:
            msg = ("You must both sign up for trips you're interested in: "
                   "you'll only be placed on a trip if you both signed up. "
                   "Either one of you can rank the trips.")
            messages.add_message(self.request, messages.INFO, msg)
        else:
            msg = "{} must also select to be paired with you".format(paired_par)
            messages.add_message(self.request, messages.INFO, msg)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(LotteryPairView, self).dispatch(request, *args, **kwargs)


class LotteryPreferencesView(TemplateView):
    template_name = 'trip_preferences.html'
    update_msg = 'Lottery preferences updated'
    car_prefix = 'car'

    @property
    def post_data(self):
        return json.loads(self.request.body) if self.request.method == "POST" else None

    @property
    def paired_par(self):
        participant = self.request.user.participant
        try:
            return participant.lotteryinfo.paired_with
        except ObjectDoesNotExist:  # No lottery info for paired participant
            return None

    @property
    def paired(self):
        """ Return if the participant is reciprocally paired with another. """
        participant = self.request.user.participant
        paired_par = self.paired_par
        if paired_par:
            try:
                return paired_par.lotteryinfo.paired_with == participant
            except ObjectDoesNotExist:
                return False
        return False

    @property
    def participant(self):
        return self.request.user.participant

    @property
    def ranked_signups(self):
        par = self.participant
        today = local_now().date()
        future_signups = models.SignUp.objects.filter(participant=par,
                                                      trip__trip_date__gt=today)
        ranked = future_signups.order_by('order', 'time_created')
        return ranked.select_related('trip')

    @property
    def ranked_signups_dict(self):
        """ Used by the Angular trip-ranking widget. """
        return [{'id': s.id, 'trip': {'id': s.trip.id, 'name': s.trip.name}}
                for s in self.ranked_signups]

    def get_car_form(self, use_post=True):
        car = self.request.user.participant.car
        post = self.post_data if use_post else None
        return forms.CarForm(post, instance=car, scope_prefix=self.car_prefix)

    def get_lottery_form(self):
        try:
            lottery_info = self.request.user.participant.lotteryinfo
        except ObjectDoesNotExist:
            lottery_info = None
        return forms.LotteryInfoForm(self.post_data, instance=lottery_info)

    def get_context_data(self):
        return {'ranked_signups': json.dumps(self.ranked_signups_dict),
                'car_form': self.get_car_form(use_post=True),
                'lottery_form': self.get_lottery_form(),
                'paired': self.paired}

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
                self.participant.car = car_form.save()
                self.participant.save()
            lottery_info = lottery_form.save(commit=False)
            lottery_info.participant = self.participant
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
        par = self.participant
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
        if not self.paired:
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
                messages.add_message(self.request, messages.WARNING, msg)
            else:
                pair_signup.order = signup.order
                pair_signup.save()

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(LotteryPreferencesView, self).dispatch(request, *args, **kwargs)


class TripMedical(TripInfoEditable):
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


class WIMPView(ListView, TripMedical, TripInfoEditable):
    model = models.Trip
    template_name = 'wimp.html'
    context_object_name = 'trips'
    form_class = forms.SummaryTripForm

    def get_queryset(self):
        trips = super(WIMPView, self).get_queryset().order_by('trip_date')
        today = local_now().date()
        return trips.filter(trip_date__gte=today)

    def get_context_data(self, **kwargs):
        context_data = super(WIMPView, self).get_context_data(**kwargs)
        by_trip = (self.get_trip_info(trip) for trip in self.get_queryset())
        all_trips = [(c['trip'], c['participants'], c['cars'], c['info_form'])
                     for c in by_trip]
        context_data['all_trips'] = all_trips
        return context_data

    @method_decorator(group_required('WSC', 'WIMP'))
    def dispatch(self, request, *args, **kwargs):
        return super(WIMPView, self).dispatch(request, *args, **kwargs)


class TripMedicalView(DetailView, LeadersOnlyView, TripMedical,
                      TripInfoEditable):
    queryset = models.Trip.objects.all()
    template_name = 'trip_medical.html'

    def get_context_data(self, **kwargs):
        """ Get a trip info form for display as readonly. """
        trip = self.get_object()
        context_data = self.get_trip_info(trip)
        context_data['participants'] = trip.signed_up_participants.filter(signup__on_trip=True)
        context_data['info_form'] = self.get_info_form(trip)
        context_data.update(self.info_form_context(trip))
        return context_data


class TripInfoView(UpdateView, LeadersOnlyView, TripInfoEditable):
    """ A hybrid view for creating/editing trip info for a given trip. """
    model = models.Trip
    context_object_name = 'trip'
    template_name = 'trip_itinerary.html'
    form_class = forms.TripInfoForm

    def get_context_data(self, **kwargs):
        context_data = super(TripInfoView, self).get_context_data(**kwargs)
        context_data.update(self.info_form_context(self.trip))
        return context_data

    def get_initial(self):
        self.trip = self.object  # Form instance will become object
        return {'trip': self.trip}

    def get_form_kwargs(self):
        kwargs = super(TripInfoView, self).get_form_kwargs()
        kwargs['instance'] = self.trip.info
        return kwargs

    def get_form(self, form_class):
        form = super(TripInfoView, self).get_form(form_class)
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
        return super(TripInfoView, self).form_valid(form)

    def get_success_url(self):
        return reverse('view_trip', args=(self.trip.id,))


class LectureAttendanceView(FormView):
    form_class = forms.AttendedLecturesForm
    template_name = 'lecture_attendance.html'
    success_url = reverse_lazy('lecture_attendance')

    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(LectureAttendanceView, self).dispatch(request, *args, **kwargs)

    def user_or_none(self, email):
        try:
            return User.objects.get(emailaddress__email=email,
                                    emailaddress__verified=True)
        except ObjectDoesNotExist:
            return None

    def form_valid(self, form):
        user = self.user_or_none(form.cleaned_data['email'])
        if user and user.check_password(form.cleaned_data['password']):
            self.record_attendance(user)
            return super(LectureAttendanceView, self).form_valid(form)
        else:
            failure_msg = 'Incorrect email + password'
            messages.add_message(self.request, messages.ERROR, failure_msg)
            return self.form_invalid(form)

    def record_attendance(self, user):
        try:
            user.participant.attended_lectures = True
        except ObjectDoesNotExist:
            msg = ("Personal info required to sign in to lectures. "
                   "Log in to your personal account, then visit this page.")
            messages.add_message(self.request, messages.ERROR, msg)
        else:
            user.participant.save()
            success_msg = 'Lecture attendance recorded for {}'.format(user.email)
            messages.add_message(self.request, messages.SUCCESS, success_msg)


class CheckTripOverflowView(View, SingleObjectMixin):
    """ JSON-returning view to be used for AJAX on trip editing. """
    model = models.Trip
    clear_response = {"msg": "",  # Returned message
                      "msg_type": ""}  # CSS class to apply

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(CheckTripOverflowView, self).dispatch(request, *args, **kwargs)

    def response_dict(self, trip, max_participants):
        """ Returns dictionary giving info about effects on the trip lists."""
        on_trip = trip.signup_set.filter(on_trip=True)
        resp = self.clear_response.copy()

        diff = max_participants - on_trip.count()
        waitlisted = models.WaitListSignup.objects.filter(signup__trip=trip)
        if diff > 0 and waitlisted[:diff]:
            bumped = ', '.join(wl.signup.participant.name for wl in waitlisted[:diff])
            resp['msg'] = ("Expanding to {} participants would bump {} off "
                           "the waitlist.".format(max_participants, bumped))
            resp['msg_type'] = 'info'
        elif diff < 0:
            bumped_signups = on_trip[max_participants:]
            bumped = ', '.join(s.participant.name for s in bumped_signups)
            resp['msg'] = ("Reducing trip to {} participants would move {} to "
                           "the waitlist.".format(max_participants, bumped))
            resp['msg_type'] = 'warning'
        return resp

    def get(self, request, *args, **kwargs):
        trip = self.get_object()
        try:
            maximum_participants = int(request.GET['maximum_participants'])
        except (KeyError, ValueError):
            resp = self.clear_response
        else:
            resp = self.response_dict(trip, maximum_participants)
        return JsonResponse(resp)
