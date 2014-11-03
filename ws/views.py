from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse, reverse_lazy
from django.db.models import Count
from django.forms.models import modelformset_factory
from django.forms import ModelForm, HiddenInput
from django.forms import widgets
from django.forms.util import ErrorList
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views.generic import (CreateView, DetailView, FormView,
                                  ListView, TemplateView, UpdateView)

from allauth.account.views import PasswordChangeView

from ws import forms
from ws import models
from ws.dateutils import local_now
from ws.decorators import group_required, user_info_required, admin_only
from ws import dateutils
from ws import message_generators
from ws import signup_utils


class LoginAfterPasswordChangeView(PasswordChangeView):
    @property
    def success_url(self):
        return reverse_lazy('account_login')

login_after_password_change = login_required(LoginAfterPasswordChangeView.as_view())


def leader_on_trip(request, trip, creator_allowed=False):
    try:
        leader = request.user.participant.leader
    except ObjectDoesNotExist:  # Only a participant
        return False
    return leader == trip.creator or leader in trip.leaders.all()


def is_wsc(request, admin_okay=True):
    wsc = bool(request.user.groups.filter(name='WSC'))
    return wsc or request.user.is_superuser and admin_okay


class UpdateParticipantView(TemplateView):
    # The Participant and EmergencyContact are both Person models, have
    # conflicting names. Use prefixes to keep them distinct in POST data
    par_prefix = "participant"
    e_prefix = "emergency_contact"

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
        par_kwargs = {"prefix": self.par_prefix, "instance": participant}
        if not participant:
            par_kwargs["initial"] = {'email': self.request.user.email}

        context = {
            'participant_form':  forms.ParticipantForm(post, **par_kwargs),
            'car_form': forms.CarForm(post, instance=car),
            'emergency_info_form':  forms.EmergencyInfoForm(post, instance=e_info),
            'emergency_contact_form':  forms.EmergencyContactForm(post, prefix=self.e_prefix, instance=e_contact),
        }
        if post:
            context['has_car_checked'] = self.has_car
        else:
            context['has_car_checked'] = bool(participant.car) if participant else True

        return context

    def post(self, request, *args, **kwargs):
        """ Validate POSTed forms, except CarForm if "no car" stated.

        Upon validation, redirect to homepage or `next` url, if specified.
        """
        context = self.get_context_data()
        required_dict = {key: val for key, val in context.items()
                         if isinstance(val, ModelForm)}

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
        try:
            car = post_forms['car_form'].save()
        except KeyError:  # No CarForm posted
            # If the Participant already existed and has a stored Car, delete it
            if participant.car:
                participant.car.delete()
                participant.car = None
        else:
            participant.car = car
        participant.save()

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(UpdateParticipantView, self).dispatch(request, *args, **kwargs)


class ParticipantDetailView(DetailView):
    queryset = models.Participant.objects.all()
    context_object_name = 'participant'
    template_name = 'participant_detail.html'

    def get_context_data(self, **kwargs):
        # By default, this method just returns a context with the object
        # However, I couldn't easily display a read-only summary of the model
        # So, this is the hackish solution
        participant = self.get_object()
        e_info = participant.emergency_info
        e_contact = e_info.emergency_contact
        context = {'participant_form': forms.ParticipantForm(instance=participant),
                   'emergency_info_form':  forms.EmergencyInfoForm(instance=e_info),
                   'emergency_contact_form':  forms.EmergencyContactForm(instance=e_contact),
                   'participant': participant,
                   }
        if participant.car:
            context['car_form'] = forms.CarForm(instance=participant.car)
        return context

    @method_decorator(group_required('leaders', 'WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(ParticipantDetailView, self).dispatch(request, *args, **kwargs)


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
        participant = self.request.user.participant
        signup = form.save(commit=False)
        signup.participant = participant
        if signup.trip in participant.trip_set.all():
            form.errors['__all__'] = ErrorList(["Already signed up!"])
            return self.form_invalid(form)
        return super(SignUpView, self).form_valid(form)

    def get_success_url(self):
        messages.add_message(self.request, messages.SUCCESS, "Signed up!")
        return reverse('view_trip', args=(self.object.trip.id,))

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(SignUpView, self).dispatch(request, *args, **kwargs)


class ViewTrip(DetailView):
    queryset = models.Trip.objects.all()
    context_object_name = 'trip'
    template_name = 'view_trip.html'

    @property
    def participant_signup(self):
        """ Return viewer's signup for this trip (if one exists, else None) """
        try:
            participant = self.request.user.participant
        except ObjectDoesNotExist:  # Logged in, no participant info
            return None
        return participant.signup_set.filter(trip=self.get_object()).first()

    def get_context_data(self, **kwargs):
        """ Create form for signup (only if signups open). """
        context = super(ViewTrip, self).get_context_data()
        trip = self.get_object()
        if trip.signups_open:
            signup_form = forms.SignUpForm(initial={'trip': trip})
            signup_form.fields['trip'].widget = HiddenInput()
            context['signup_form'] = signup_form
        signups = models.SignUp.objects.filter(trip=trip)
        signups = signups.select_related('participant')
        context['participant_signup'] = self.participant_signup
        context['signups'] = signups
        context['has_notes'] = trip.notes or any(s.notes for s in signups)
        context['signups_on_trip'] = signups.filter(on_trip=True)
        return context

    def get(self, request, *args, **kwargs):
        trip = self.get_object()
        if leader_on_trip(request, trip):
            return redirect(reverse('admin_trip', args=(trip.id,)))
        return super(ViewTrip, self).get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """ Add signup to trip or waitlist, if applicable. """
        signup_utils.trip_or_wait(self.participant_signup, self.request)
        return self.get(request)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ViewTrip, self).dispatch(request, *args, **kwargs)


class AdminTripView(DetailView):
    model = models.Trip
    template_name = 'admin_trip.html'
    par_prefix = "ontrip"
    wl_prefix = "waitlist"


    @property
    def signup_formset(self):
        return modelformset_factory(models.SignUp, can_delete=True, extra=0,
                                    fields=())  # on_trip to manage wait list

    def get_context_data(self, **kwargs):
        trip = self.get_object()
        trip_signups = models.SignUp.objects.filter(trip=trip)
        post = self.request.POST if self.request.method == "POST" else None
        ontrip_queryset = trip_signups.filter(on_trip=True)
        ontrip_formset = self.signup_formset(post, queryset=ontrip_queryset,
                                             prefix=self.par_prefix)

        wl_queryset = trip_signups.filter(waitlist__isnull=False)
        wl_queryset = wl_queryset.order_by('waitlistsignup')
        waitlist_formset = self.signup_formset(post, queryset=wl_queryset,
                                               prefix=self.wl_prefix)
        # For manual waitlist managament, enable deletion, disable some signals
        waitlist_formset.can_delete = False
        today = local_now().date()
        return {"ontrip_signups": ontrip_queryset,
                "ontrip_formset": ontrip_formset,
                "waitlist_formset": waitlist_formset,
                "signups": trip_signups,
                "trip": trip,
                "trip_completed": today >= trip.trip_date}

    def post(self, request, *args, **kwargs):
        """ Two formsets handle adding/removing people from trip. """
        context = self.get_context_data()
        ontrip_formset = context['ontrip_formset']
        waitlist_formset = context['waitlist_formset']
        if (ontrip_formset.is_valid() and waitlist_formset.is_valid()):
            ontrip_formset.save()
            # Anybody added from waitlist needs to be removed from waitlist
            for signup in waitlist_formset.save():
                # NOTE: this only applies for manual waitlist management
                # Manual management needs the `on_trip` field, and for the
                # pre_delete SignUp signal to be deactivated
                if signup.on_trip:
                    signup.waitlistsignup.delete()
                    signup.save()
            messages.add_message(request, messages.SUCCESS, "Updated trip")
        return self.get(request, *args, **kwargs)

    @method_decorator(group_required('leaders', 'WSC'))
    def dispatch(self, request, *args, **kwargs):
        """ Only allow trip creator, leaders of this trip and WSC to edit. """
        trip = self.get_object()
        wsc = is_wsc(request)
        if not (leader_on_trip(request, trip, creator_allowed=True) or wsc):
            return render(request, 'not_your_trip.html')
        return super(AdminTripView, self).dispatch(request, *args, **kwargs)


class ReviewTripView(DetailView):
    queryset = models.Trip.objects.all()
    context_object_name = 'trip'
    template_name = 'review_trip.html'
    success_msg = "Thanks for your feedback"

    @property
    def feedback_formset(self):
        return modelformset_factory(models.Feedback, extra=0)

    def post(self, request, *args, **kwargs):
        feedback_list = self.feedback_list
        if all(form.is_valid() for participant, form in feedback_list):
            leader = request.user.participant.leader
            trip = self.get_object()
            for participant, form in feedback_list:
                feedback = form.save(commit=False)
                feedback.leader = leader
                feedback.participant = participant
                feedback.trip = trip
                form.save()

            messages.add_message(request, messages.SUCCESS, self.success_msg)
            return redirect(reverse('home'))
        return self.get(request, *args, **kwargs)

    @property
    def trip_participants(self):
        trip = self.get_object()
        accepted_signups = trip.signup_set.filter(on_trip=True)
        accepted_signups = accepted_signups.select_related('participant')
        return [signup.participant for signup in accepted_signups]

    def get_existing_feedback(self, participant, leader):
        trip = self.get_object()
        feedback = models.Feedback.objects.filter(participant=participant,
                                                  trip=trip, leader=leader)
        return feedback.first() or None

    @property
    def feedback_list(self):
        post = self.request.POST if self.request.method == 'POST' else None
        leader = self.request.user.participant.leader
        feedback_list = []
        for participant in self.trip_participants:
            instance = self.get_existing_feedback(participant, leader)
            initial = {'participant': participant}
            form = forms.FeedbackForm(post, instance=instance, initial=initial,
                                      prefix=participant.id)
            feedback_list.append((participant, form))
        return feedback_list

    def get_context_data(self, **kwargs):
        today = local_now().date()
        trip = self.get_object()
        return {"trip": trip, "trip_completed": today >= trip.trip_date,
                "feedback_list": self.feedback_list}

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        if not leader_on_trip(request, self.get_object()):
            return render(request, 'not_your_trip.html')
        return super(ReviewTripView, self).dispatch(request, *args, **kwargs)


def home(request):
    message_generators.warn_if_needs_update(request)
    message_generators.complain_if_missing_feedback(request)

    lottery_messages = message_generators.LotteryMessages(request)
    lottery_messages.supply_all_messages()
    return render(request, 'home.html')


class BecomeLeader(CreateView):
    template_name = "become_leader.html"
    model = models.LeaderApplication
    fields = ['previous_rating', 'desired_rating', 'taking_wfa',
              'training', 'winter_experience', 'other_experience',
              'notes_or_comments']

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(BecomeLeader, self).dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        """ Link the application to the submitting participant. """
        application = form.save(commit=False)
        application.participant = self.request.user.participant
        received = "Leader application received!"
        messages.add_message(self.request, messages.SUCCESS, received)
        return super(BecomeLeader, self).form_valid(form)

    def get_context_data(self, **kwargs):
        """ Give next year's value in the context. """
        context_data = super(BecomeLeader, self).get_context_data(**kwargs)
        context_data['year'] = local_now().date().year + 1
        return context_data

    def get_success_url(self):
        return reverse('home')


class AllLeaderApplications(ListView):
    model = models.LeaderApplication
    context_object_name = 'leader_applications'
    template_name = 'manage_applications.html'

    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(AllLeaderApplications, self).dispatch(request, *args, **kwargs)


class LeaderApplicationView(DetailView):
    model = models.LeaderApplication
    context_object_name = 'application'
    template_name = 'view_application.html'

    def get_context_data(self, **kwargs):
        """ Add on a form to assign/modify leader permissions. """
        context_data = super(LeaderApplicationView, self).get_context_data(**kwargs)
        application = self.get_object()
        leader = self.get_leader(application)
        initial = {'participant': application.participant}
        leader_form = forms.LeaderForm(instance=leader, initial=initial)
        leader_form.fields['participant'].widget = HiddenInput()

        context_data['leader_form'] = leader_form
        return context_data

    def get_leader(self, application):
        """ Get the existing leader instance, if there is one. """
        try:
            return application.participant.leader
        except ObjectDoesNotExist:
            return None

    def post(self, request, *args, **kwargs):
        """ Save a rating for the leader. """
        application = self.get_object()
        leader_form = forms.LeaderForm(request.POST, instance=self.get_leader(application))

        if leader_form.is_valid():
            leader_form.save()
            leader = leader_form.instance
            update_msg = "{} given {} rating".format(leader.participant.name,
                                                     leader.rating)
            messages.add_message(request, messages.SUCCESS, update_msg)
            return redirect(reverse('manage_applications'))
        elif not leader_form.instance.rating:  # Assume to mean "no leader"
            msg = "{} not given a leader rating".format(application.participant)
            messages.add_message(request, messages.INFO, msg)
            return redirect(reverse('manage_applications'))

        else:  # Any miscellaneous error form could possibly produce
            return render(request, 'add_leader.html', {'leader_form': leader_form})

    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(LeaderApplicationView, self).dispatch(request, *args, **kwargs)


@group_required('WSC')
def add_leader(request):
    """ Create a Leader record for an existing Participant. """
    if request.method == "POST":
        form = forms.LeaderForm(request.POST)
        if form.is_valid():
            form.save()
            messages.add_message(request, messages.SUCCESS, 'Added new leader')
    else:
        # Regardless of success, empty form for quick addition of another
        form = forms.LeaderForm()
    return render(request, 'add_leader.html', {'leader_form': form})


@group_required('WSC')
def manage_leaders(request):
    LeaderFormSet = modelformset_factory(models.Leader, can_delete=True, extra=0,
                                         exclude=('participant',),
                                         widgets={'notes': widgets.TextInput})
    if request.method == 'POST':
        formset = LeaderFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated leaders')
            formset = LeaderFormSet()  # Render updated forms
    else:
        leaders = models.Leader.objects.all().select_related('participant')
        formset = LeaderFormSet(queryset=leaders)
    return render(request, 'manage_leaders.html', {'formset': formset})


@group_required('WSC')
def manage_participants(request):
    ParticipantFormSet = modelformset_factory(models.Participant, can_delete=True, extra=0,
                                              fields=('attended_lectures',))
    if request.method == 'POST':
        formset = ParticipantFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated participants')
            formset = ParticipantFormSet()
    else:
        cutoff = dateutils.participant_cutoff()
        current = models.Participant.objects.filter(last_updated__gt=cutoff)
        current = current.select_related('leader')
        # TODO: participant.num_trips uses signup_set, adds n extra queries
        formset = ParticipantFormSet(queryset=current)
    return render(request, 'manage_participants.html', {'formset': formset})


def _manage_trips(request, TripFormSet):
    if request.method == 'POST':
        formset = TripFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated trips')
            formset = TripFormSet()
    else:
        all_trips = models.Trip.objects.all()
        # FIXME: Doesn't seem to reduce query count
        all_trips.select_related('leaders__participant')
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
                                       fields=('algorithm', 'wsc_approved'))
    return _manage_trips(request, TripFormSet)


class AddTrip(CreateView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = 'add_trip.html'

    def get_success_url(self):
        return reverse('view_trip', args=(self.object.id,))

    def get_initial(self):
        """ Default with trip creator among leaders. """
        initial = super(AddTrip, self).get_initial().copy()
        try:
            initial['leaders'] = [self.request.user.participant.leader]
        except ObjectDoesNotExist:  # WSC (with no Leader) tries to add trip
            pass
        return initial

    def form_valid(self, form):
        """ After is_valid(), assign creator from User, add empty waitlist. """
        creator = self.request.user.participant.leader
        trip = form.save(commit=False)
        trip.creator = creator
        return super(AddTrip, self).form_valid(form)

    @method_decorator(group_required('WSC', 'leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super(AddTrip, self).dispatch(request, *args, **kwargs)


class EditTrip(UpdateView):
    model = models.Trip
    form_class = forms.TripForm
    template_name = 'edit_trip.html'

    @method_decorator(group_required('leaders', 'WSC'))
    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        wsc = is_wsc(request)
        if not (leader_on_trip(request, trip, creator_allowed=True) or wsc):
            return render(request, 'not_your_trip.html')
        return super(EditTrip, self).dispatch(request, *args, **kwargs)

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
        if not is_wsc(self.request):
            trip.wsc_approved = False
        return super(EditTrip, self).form_valid(form)


class TripListView(ListView):
    """ Superclass for any view that displays a list of trips. """
    model = models.Trip
    template_name = 'view_trips.html'
    context_object_name = 'trip_queryset'
    form_class = forms.SummaryTripForm

    def get_queryset(self):
        # Each trip will need information about its leaders, so prefetch models
        trips = super(TripListView, self).get_queryset()
        trips = trips.annotate(num_signups=Count('signup'))
        return trips.prefetch_related('leaders__participant')

    def get_context_data(self, **kwargs):
        """ Sort trips into past and present trips. """
        context_data = super(TripListView, self).get_context_data(**kwargs)
        context_data['current_trips'], context_data['past_trips'] = [], []
        today = local_now().date()
        for trip in context_data[self.context_object_name]:
            if trip.trip_date >= today:
                context_data['current_trips'].append(trip)
            else:
                context_data['past_trips'].append(trip)
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


class ViewTrips(CurrentTripListView):
    """ View current trips. """
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class ViewAllTrips(TripListView):
    """ View all trips, past and present. """
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class ViewParticipantTrips(TripListView):
    """ View trips the user is a participant on. """
    template_name = 'view_my_trips.html'

    def get_queryset(self):
        participant = self.request.user.participant
        accepted_signups = participant.signup_set.filter(on_trip=True)

        trips = super(ViewParticipantTrips, self).get_queryset()
        return trips.filter(signup__in=accepted_signups)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class ViewWaitlistTrips(TripListView):
    """ View trips the user is currently waitlisted on. """
    def get_queryset(self):
        signups = self.request.user.participant.signup_set
        waitlisted_signups = signups.filter(waitlistsignup__isnull=False)

        trips = super(ViewWaitlistTrips, self).get_queryset()
        return trips.filter(signup__in=waitlisted_signups)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class ViewLeaderTrips(TripListView):
    """ View trips the user is leading. """
    def get(self, request, *args, **kwargs):
        leader = request.user.participant.leader
        self.queryset = leader.trip_set.all()
        return super(ViewLeaderTrips, self).get(request, *args, **kwargs)

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super(ViewLeaderTrips, self).dispatch(request, *args, **kwargs)


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


class TripPreferencesView(TemplateView):
    template_name = 'trip_preferences.html'
    update_msg = 'Lottery preferences updated'

    @property
    def post_data(self):
        return self.request.POST if self.request.method == "POST" else None

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
    def factory_formset(self):
        return modelformset_factory(models.SignUp, can_delete=True, extra=0,
                                    fields=('order',))

    def get_ranked_trips(self, participant):
        today = local_now().date()
        future_trips = models.SignUp.objects.filter(participant=participant,
                                                    trip__trip_date__gt=today)
        ranked_trips = future_trips.order_by('order', 'time_created')
        return ranked_trips.select_related('trip')

    def get_car_form(self, use_post=True):
        car = self.request.user.participant.car
        post = self.post_data if use_post else None
        return forms.CarForm(post, instance=car)

    def get_formset(self, use_post=True):
        ranked_trips = self.get_ranked_trips(self.request.user.participant)
        post = self.post_data if use_post else None
        return self.factory_formset(post, queryset=ranked_trips)

    def get_lottery_form(self):
        try:
            lottery_info = self.request.user.participant.lotteryinfo
        except ObjectDoesNotExist:
            lottery_info = None
        return forms.LotteryInfoForm(self.post_data, instance=lottery_info)

    def get_context_data(self):
        return {"formset": self.get_formset(use_post=True),
                'car_form': self.get_car_form(use_post=True),
                'lottery_form': self.get_lottery_form(),
                'paired': self.paired}

    def post(self, request, *args, **kwargs):
        context = self.get_context_data()
        lottery_form, formset = context['lottery_form'], context['formset']
        car_form = context['car_form']
        skip_car_form = lottery_form.data['car_status'] != 'own'
        car_form_okay = skip_car_form or car_form.is_valid()
        if (lottery_form.is_valid() and formset.is_valid() and car_form_okay):
            if skip_car_form:  # New form so submission doesn't show errors
                context['car_form'] = self.get_car_form(use_post=False)
            else:
                request.user.participant.car = car_form.save()
            lottery_info = lottery_form.save(commit=False)
            lottery_info.participant = request.user.participant
            lottery_info.save()
            self.save_signups(formset)
            messages.add_message(request, messages.SUCCESS, self.update_msg)
            context['formset'] = self.get_formset(use_post=False)
        return render(request, self.template_name, context)

    def save_signups(self, formset):
        formset.save()
        if not self.paired:
            return

        paired_par = self.paired_par
        # Don't just iterate through saved forms. This could miss signups
        # that participant ranks, then the other signs up for later
        for signup in (form.instance for form in formset):
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
        return super(TripPreferencesView, self).dispatch(request, *args, **kwargs)


class TripMedical(object):
    def get_trip_info(self, trip):
        signups = trip.signup_set.filter(on_trip=True)
        on_trip = (Q(participant__leader__in=trip.leaders.all()) |
                   Q(participant__signup__in=signups))
        cars = models.Car.objects.filter(on_trip).distinct()
        cars = cars.select_related('participant__lotteryinfo')
        signups = signups.select_related('participant__emergency_info')
        return {'trip': trip, 'signups': signups, 'cars': cars}


class WIMPView(ListView, TripMedical):
    model = models.Trip
    template_name = 'wimp.html'
    context_object_name = 'trips'
    form_class = forms.SummaryTripForm

    def get_queryset(self):
        trips = super(WIMPView, self).get_queryset()
        today = local_now().date()
        return trips.filter(trip_date__gte=today)

    def get_context_data(self, **kwargs):
        context_data = super(WIMPView, self).get_context_data(**kwargs)
        by_trip = (self.get_trip_info(trip) for trip in self.get_queryset())
        context_data['foo'] = [(c['trip'], c['signups'], c['cars'])
                               for c in by_trip]
        return context_data

    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(WIMPView, self).dispatch(request, *args, **kwargs)


class TripMedicalView(DetailView, TripMedical):
    queryset = models.Trip.objects.all()
    template_name = 'trip_medical.html'

    def get_context_data(self, **kwargs):
        return self.get_trip_info(self.get_object())

    @method_decorator(group_required('leaders', 'WSC'))
    def dispatch(self, request, *args, **kwargs):
        """ Only allow trip creator, leaders of this trip and WSC to view. """
        trip = self.get_object()
        wsc = is_wsc(request)
        if not (leader_on_trip(request, trip, creator_allowed=True) or wsc):
            return render(request, 'not_your_trip.html')
        return super(TripMedicalView, self).dispatch(request, *args, **kwargs)


class LectureAttendanceView(FormView):
    form_class = forms.AttendedLecturesForm
    template_name = 'lecture_attendance.html'
    success_url = reverse_lazy('lecture_attendance')

    @method_decorator(group_required('WSC'))
    def dispatch(self, request, *args, **kwargs):
        return super(LectureAttendanceView, self).dispatch(request, *args, **kwargs)

    def user_or_none(self, email):
        try:
            return User.objects.get(email=email)
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
        user.participant.attended_lectures = True
        user.participant.save()
        success_msg = 'Lecture attendance recorded for {}'.format(user.email)
        messages.add_message(self.request, messages.SUCCESS, success_msg)
