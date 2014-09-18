from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.urlresolvers import reverse
from django.forms.models import modelformset_factory
from django.forms import ModelForm, HiddenInput
from django.forms.util import ErrorList
from django.shortcuts import render, redirect
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DetailView, ListView, View

from ws import forms
from ws import models
from ws.decorators import group_required, user_info_required
from ws import message_generators


def leader_on_trip(request, trip, creator_allowed=False):
    try:
        leader = request.user.participant.leader
    except ObjectDoesNotExist:  # Only a participant
        return False
    return leader == trip.creator or leader in trip.leaders.all()


class UpdateParticipantView(View):
    # The Participant and EmergencyContact are both Person models, have
    # conflicting names. Use prefixes to keep them distinct in POST data
    par_prefix = "participant"
    e_prefix = "emergency_contact"

    template_name = 'update_info.html'
    update_msg = 'Personal information updated successfully'

    def _has_car(self, request):
        return 'has_car' in request.POST

    def _participant(self, request):
        try:
            return request.user.participant
        except ObjectDoesNotExist:
            return None

    def get_context_data(self, request):
        """ Return a dictionary primarily of forms to for template rendering.
        Also includes a value for the "I have a car" checkbox.

        Outputs three types of forms:
            - Bound forms, if POSTed
            - Empty forms if GET, and no stored Participant data
            - Filled forms if GET, and Participant data exists

        Forms are bound to model instances for UPDATE if such instances exist.
        """
        post = request.POST if request.method == "POST" else None
        participant = self._participant(request)

        # Access other models within participant
        car = participant and participant.car
        e_info = participant and participant.emergency_info
        e_contact = e_info and e_info.emergency_contact

        # If no Participant object, fill at least with User email
        par_kwargs = {"prefix": self.par_prefix, "instance": participant}
        if not participant:
            par_kwargs["initial"] = {'email': request.user.email}

        context = {
            'participant_form':  forms.ParticipantForm(post, **par_kwargs),
            'car_form': forms.CarForm(post, instance=car),
            'emergency_info_form':  forms.EmergencyInfoForm(post, instance=e_info),
            'emergency_contact_form':  forms.EmergencyContactForm(post, prefix=self.e_prefix, instance=e_contact),
        }
        if post:
            context['has_car_checked'] = self._has_car(request)
        else:
            context['has_car_checked'] = bool(participant.car) if participant else True

        return context

    def get(self, request, *args, **kwargs):
        context = self.get_context_data(request)
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        """ Validate POSTed forms, except CarForm if "no car" stated.

        Upon validation, redirect to homepage or `next` url, if specified.
        """
        context = self.get_context_data(request)
        required_dict = {key: val for key, val in context.items()
                         if isinstance(val, ModelForm)}

        if not self._has_car(request):
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

    @method_decorator(group_required('WSC'))
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

    def get_context_data(self, **kwargs):
        """ Create form for signup (only if signups open). """
        context = super(ViewTrip, self).get_context_data()
        trip = self.get_object()
        if trip.signups_open:
            signup_form = forms.SignUpForm(initial={'trip': trip})
            signup_form.fields['trip'].widget = HiddenInput()
            context['signup_form'] = signup_form
        signups = models.SignUp.objects.filter(trip=trip)
        context['signups'] = signups
        context['signups_on_trip'] = signups.filter(on_trip=True)
        return context

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(ViewTrip, self).dispatch(request, *args, **kwargs)


class AdminTripView(DetailView):
    model = models.Trip
    template_name = 'admin_trip.html'
    par_prefix = "ontrip"
    wl = "waitlist"

    @property
    def signup_formset(self):
        return modelformset_factory(models.SignUp, can_delete=True, extra=0,
                                    fields=('on_trip',))

    def get_context(self, request, use_post=True):
        trip = self.get_object()
        trip_signups = models.SignUp.objects.filter(trip=trip)
        post = request.POST if use_post and request.method == "POST" else None
        ontrip_queryset = trip_signups.filter(on_trip=True)
        ontrip_formset = self.signup_formset(post, queryset=ontrip_queryset,
                                             prefix=self.par_prefix)

        waitlist_queryset = trip_signups.filter(waitlist__isnull=False)
        waitlist_formset = self.signup_formset(post, queryset=waitlist_queryset,
                                               prefix=self.wl)
        return {"ontrip_formset": ontrip_formset,
                "waitlist_formset": waitlist_formset,
                "trip": trip}

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context(request))

    def post(self, request, *args, **kwargs):
        """ Two formsets handle adding/removing people from trip. """
        context = self.get_context(request)
        ontrip_formset = context['ontrip_formset']
        waitlist_formset = context['waitlist_formset']
        if (ontrip_formset.is_valid() and waitlist_formset.is_valid()):
            ontrip_formset.save()
            # Anybody added from waitlist needs to be removed from waitlist
            for signup in waitlist_formset.save():
                if signup.on_trip:
                    signup.waitlistsignup.delete()
                    signup.save()
            messages.add_message(request, messages.SUCCESS, "Updated trip")
            context = self.get_context(request, use_post=False)
        return render(request, self.template_name, context)

    @method_decorator(group_required('leaders', 'WSC'))
    def dispatch(self, request, *args, **kwargs):
        """ Only allow trip creator, leaders of this trip and WSC to edit. """
        trip = self.get_object()
        is_wsc = bool(request.user.groups.filter(name='WSC'))
        # NOTE: Fixed logic here
        if not (leader_on_trip(request, trip, creator_allowed=True) or is_wsc):
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

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context(request))

    def post(self, request, *args, **kwargs):
        feedback_list = self.get_feedback_list(request)
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
        context = self.get_context(request)
        return render(request, self.template_name, context)

    @property
    def trip_participants(self):
        trip = self.get_object()
        accepted_signups = trip.signup_set.filter(on_trip=True)
        return [signup.participant for signup in accepted_signups]

    def get_existing_feedback(self, participant, leader):
        trip = self.get_object()
        feedback = models.Feedback.objects.filter(participant=participant,
                                                  trip=trip, leader=leader)
        return feedback.first() or None

    def get_feedback_list(self, request):
        post = request.POST if request.method == 'POST' else None
        leader = request.user.participant.leader
        feedback_list = []
        for participant in self.trip_participants:
            instance = self.get_existing_feedback(participant, leader)
            initial = {'participant': participant}
            form = forms.FeedbackForm(post, instance=instance, initial=initial,
                                      prefix=participant.id)
            feedback_list.append((participant, form))
        return feedback_list

    def get_context(self, request):
        feedback_list = self.get_feedback_list(request)
        return {"trip": self.get_object(), "feedback_list": feedback_list}

    @method_decorator(group_required('leaders'))
    def dispatch(self, request, *args, **kwargs):
        if not leader_on_trip(request, self.get_object()):
            return render(request, 'not_your_trip.html')
        return super(ReviewTripView, self).dispatch(request, *args, **kwargs)


def home(request):
    message_generators.warn_if_needs_update(request)
    message_generators.complain_if_missing_feedback(request)
    return render(request, 'home.html')


#@permission_required('ws.can_add_leader', raise_exception=True)
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
                                         exclude=('participant',))
    if request.method == 'POST':
        formset = LeaderFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated leaders')
            formset = LeaderFormSet()  # Render updated forms
    else:
        formset = LeaderFormSet()
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
        formset = ParticipantFormSet()
    return render(request, 'manage_participants.html', {'formset': formset})


@group_required('WSC')
def manage_trips(request):
    TripFormSet = modelformset_factory(models.Trip, can_delete=True, extra=0,
                                       fields=('algorithm', 'wsc_approved'))
    if request.method == 'POST':
        formset = TripFormSet(request.POST)
        if formset.is_valid():
            formset.save()
            messages.add_message(request, messages.SUCCESS, 'Updated trips')
            formset = TripFormSet()
    else:
        formset = TripFormSet()
    return render(request, 'manage_trips.html', {'formset': formset})


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
        # TODO: Warn if the creator isn't one of the trip leaders,
        # Prompt them to edit the trip, add themselves
        trip.save()  # Means it'll be saved twice...
        trip.waitlist = models.WaitList.objects.create(trip=trip)
        return super(AddTrip, self).form_valid(form)

    @method_decorator(group_required('WSC', 'leaders'))
    def dispatch(self, request, *args, **kwargs):
        return super(AddTrip, self).dispatch(request, *args, **kwargs)


class TripListView(ListView):
    model = models.Trip
    template_name = 'view_trips.html'
    context_object_name = 'trip_list'
    form_class = forms.SummaryTripForm


class ViewTrips(TripListView):
    """ View all trips. """
    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class ViewParticipantTrips(TripListView):
    """ View trips the user is a participant on. """
    def get(self, request, *args, **kwargs):
        participant = request.user.participant
        accepted_signups = participant.signup_set.filter(on_trip=True)
        self.queryset = [signup.trip for signup in accepted_signups]
        return super(TripListView, self).get(request, *args, **kwargs)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripListView, self).dispatch(request, *args, **kwargs)


class ViewWaitlistTrips(TripListView):
    """ View trips the user is currently waitlisted on. """
    def get(self, request, *args, **kwargs):
        signups = request.user.participant.signup_set
        waitlisted_signups = signups.filter(waitlistsignup__isnull=False)
        self.queryset = [signup.trip for signup in waitlisted_signups]
        return super(TripListView, self).get(request, *args, **kwargs)

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


class TripPreferencesView(View):
    template_name = 'trip_preferences.html'
    update_msg = 'Lottery preferences updated'

    @property
    def factory_formset(self):
        return modelformset_factory(models.SignUp, can_delete=True, extra=0,
                                    fields=('order',))

    def get_formset(self, request, use_post=True):
        participant = request.user.participant
        queryset = models.SignUp.objects.filter(participant=participant)
        ranked_queryset = queryset.order_by('order', 'time_created')
        post = request.POST if use_post and request.method == "POST" else None
        return self.factory_formset(post, queryset=ranked_queryset)

    def get_lottery_form(self, request):
        post = request.POST if request.method == "POST" else None
        try:
            lottery_info = request.user.participant.lotteryinfo
        except ObjectDoesNotExist:
            lottery_info = None
        return forms.LotteryInfoForm(post, instance=lottery_info)

    def get_context(self, request):
        return {"formset": self.get_formset(request),
                "lottery_form": self.get_lottery_form(request)}

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self.get_context(request))

    def post(self, request, *args, **kwargs):
        context = self.get_context(request)
        lottery_form, formset = context['lottery_form'], context['formset']
        if (lottery_form.is_valid() and formset.is_valid()):
            lottery_info = lottery_form.save(commit=False)
            lottery_info.participant = request.user.participant
            lottery_info.save()
            formset.save()
            messages.add_message(request, messages.SUCCESS, self.update_msg)
            context['formset'] = self.get_formset(request, use_post=False)
        return render(request, self.template_name, context)

    @method_decorator(user_info_required)
    def dispatch(self, request, *args, **kwargs):
        return super(TripPreferencesView, self).dispatch(request, *args, **kwargs)
