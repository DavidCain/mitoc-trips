import json

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.generic import (DetailView, ListView, View)
from django.views.generic.detail import SingleObjectMixin
from django.utils.decorators import method_decorator
import jwt

from ws import models
from ws.views import AllLeadersView, TripLeadersOnlyView
from ws.templatetags.gravatar import gravatar_url

from ws.utils.api import jwt_token_from_headers
from ws.utils.model_dates import missed_lectures
from ws.utils.dates import date_from_iso
import ws.utils.perms as perm_utils
import ws.utils.signups as signup_utils
import ws.utils.geardb as geardb_utils


class SimpleSignupsView(DetailView):
    """ Give the name and email of leaders and signed up participants. """
    model = models.Trip

    def get(self, request, *args, **kwargs):
        trip = self.get_object()

        on_trip = trip.signed_up_participants.filter(signup__on_trip=True)
        signups = {
            'onTrip': on_trip.values('name', 'email'),
            'waitlist': [{'name': s.participant.name, 'email': s.participant.email}
                         for s in trip.waitlist.signups],
        }
        participant_signups = {}
        for key, participants in signups.items():
            participant_signups[key] = [{'participant': par} for par in participants]

        return JsonResponse({
            'signups': participant_signups,
            'leaders': list(trip.leaders.values('name', 'email')),
            'creator': {
                'name': trip.creator.name,
                'email': trip.creator.email,
            },
        })

    def dispatch(self, request, *args, **kwargs):
        """ Participant object must exist, but it need not be current. """
        if not self.request.participant:
            return JsonResponse({}, status=403)
        return super().dispatch(request, *args, **kwargs)


class FormatSignupMixin:
    def describe_signup(self, signup, trip_participants, other_signups_by_par):
        """ Yield everything used in the participant-selecting modal.

        The signup object should come with related models already selected,
        or this could result in a _lot_ of extra queries.

        :param signup: An models.SignUp instance (either on trip or waitlisted)
        :param trip_participants: All Participants that are on the same trip
        :param other_signups_by_par: For each participant on this trip,
                                     other trips they're on this weekend(ish)
        """
        par = signup.participant

        # In rare cases, a trip creator can be a participant on their own trip
        # Be sure we hide feedback from them if this is the case
        hide_feedback = signup.participant == self.request.participant
        feedback = [] if hide_feedback else par.feedback_set.all()

        try:
            lotteryinfo = par.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            lotteryinfo = None

        num_passengers = lotteryinfo and lotteryinfo.number_of_passengers

        # Show 'paired with' only if that user is also on the trip
        paired_with = lotteryinfo and lotteryinfo.reciprocally_paired_with
        if paired_with not in trip_participants:  # Includes waitlist!
            paired_with = None

        if signup.trip.activity == 'winter_school':
            no_lectures = missed_lectures(par, signup.trip.trip_date.year)
        else:
            no_lectures = False  # Don't show warning for other activities

        other_signups = other_signups_by_par[par.pk]

        return {
            'id': signup.id,
            'participant': {'id': par.id, 'name': par.name, 'email': par.email},
            'missed_lectures': no_lectures,
            'feedback': [
                {
                    'showed_up': f.showed_up,
                    'leader': f.leader.name,
                    'comments': f.comments,
                    'trip': {'id': f.trip.id, 'name': f.trip.name}
                } for f in feedback
            ],
            'also_on': [{'id': s.trip.id, 'name': s.trip.name} for s in other_signups],
            'paired_with': ({'id': paired_with.pk, 'name': paired_with.name}
                            if paired_with else None),
            'car_status': lotteryinfo and lotteryinfo.car_status,
            'number_of_passengers': num_passengers,
            'notes': signup.notes
        }


class AdminTripSignupsView(SingleObjectMixin, FormatSignupMixin,
                           TripLeadersOnlyView):
    model = models.Trip

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

    def get_signups(self):
        """ Trip signups with selected models for use in describe_signup. """
        trip = self.get_object()
        return (
            trip.signup_set
            .filter(Q(on_trip=True) | Q(waitlistsignup__isnull=False))
            .select_related('participant',
                            'participant__lotteryinfo__paired_with__lotteryinfo')
            .prefetch_related('participant__feedback_set',
                              'participant__feedback_set__leader',
                              'participant__feedback_set__trip')
            .order_by('-on_trip', 'waitlistsignup', 'last_updated')
        )

    def describe_all_signups(self):
        """ Get information about the trip's signups. """
        trip = self.get_object()
        signups = self.get_signups()

        trip_participants = {s.participant for s in signups}
        other_signups_by_par = {s.participant.pk: [] for s in signups}
        for other_signup in trip.other_signups.select_related('trip'):
            other_signups_by_par[other_signup.participant.pk].append(other_signup)

        return {
            'signups': [self.describe_signup(s, trip_participants, other_signups_by_par)
                        for s in self.get_signups()],
            'leaders': list(trip.leaders.values('name', 'email')),
            'creator': {
                'name': trip.creator.name,
                'email': trip.creator.email,
            },
        }

    def get(self, request, *args, **kwargs):
        return JsonResponse(self.describe_all_signups())


class LeaderParticipantSignupView(SingleObjectMixin, FormatSignupMixin,
                                  TripLeadersOnlyView):
    model = models.Trip

    def post(self, request, *args, **kwargs):
        """ Process the participant & trip, create or update signup as neeeded.

        This method handles two main cases:
        - Participant has never signed up for the trip, will be placed
        - Participant has signed up before, but is not on the trip
        """

        postdata = json.loads(self.request.body)
        par_pk = postdata.get('participant_id')

        try:
            par = models.Participant.objects.get(pk=par_pk)
        except ObjectDoesNotExist:
            return JsonResponse({'message': "No participant found"}, status=404)

        trip = self.get_object()
        signup, created = models.SignUp.objects.get_or_create(trip=trip, participant=par)
        if signup.on_trip and not created:
            # Other cases: Exists but not on trip, or exists but on waitlist
            # (trip_or_wait will handle both of those cases)
            msg = "{} is already signed up".format(signup.participant.name)
            return JsonResponse({'message': msg}, status=409)

        signup.notes = postdata.get('notes', '')
        signup = signup_utils.trip_or_wait(signup)

        other_signups = {par.pk: trip.other_signups.filter(participant=par)}

        # signup: descriptor, agnostic of presence on the trip or waiting list
        # on_trip: a boolean to place this signup in the right place
        #          (either at the bottom of the trip list or waiting list)
        return JsonResponse({'signup': self.describe_signup(signup, other_signups),
                             'on_trip': signup.on_trip}, status=201)


class JsonAllParticipantsView(ListView):
    model = models.Participant

    def render_to_response(self, context, **response_kwargs):
        participants = self.get_queryset()
        search = self.request.GET.get('search')
        if search:
            # This search is not indexed, or particularly advanced
            # TODO: Use Postgres FTS, either in raw SQL or through ORM
            # (Django 1.10 introduces support for full-text search)
            match = (Q(name__icontains=search) |
                     Q(email__icontains=search))
            participants = participants.filter(match)
        if self.request.GET.get('exclude_self'):
            participants = participants.exclude(pk=self.request.participant.pk)
        top_matches = participants[:20].values('name', 'email', 'id')
        return JsonResponse({'participants': list(top_matches)})

    def dispatch(self, request, *args, **kwargs):
        """ Participant object must exist, but it need not be current. """
        if not self.request.participant:
            return JsonResponse({}, status=403)
        return super().dispatch(request, *args, **kwargs)


class JsonAllLeadersView(AllLeadersView):
    """ Give basic information about leaders, viewable to the public. """
    def get_queryset(self):
        leaders = super().get_queryset()
        activity = self.kwargs.get('activity')
        if activity:
            leaders = leaders.filter(leaderrating__activity=activity,
                                     leaderrating__active=True).distinct()
        return leaders

    def render_to_response(self, context, **response_kwargs):
        user_is_leader = perm_utils.is_leader(self.request.user)
        all_leaders = []
        for leader in self.get_queryset():
            json_leader = {
                'id': leader.id,
                'name': leader.name,
                # Use 200x200 for Retina display at 100x100 on mitoc.mit.edu
                'gravatar': gravatar_url(leader.email, 200)
            }

            # Full roster of leaders by rating is not meant to be public
            if user_is_leader:
                active_ratings = leader.leaderrating_set.filter(active=True)
                select_fields = active_ratings.values("activity", "rating")
                json_leader['ratings'] = list(select_fields)

            all_leaders.append(json_leader)

        return JsonResponse({'leaders': all_leaders})

    # Give leader names and Gravatars to the public
    # (Gravatar URLs hash the email with MD5)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


@login_required
def get_rating(request, pk, activity):
    query = Q(participant__pk=pk, activity=activity, active=True)
    lr = models.LeaderRating.objects.filter(query).values('rating', 'notes')
    return JsonResponse(lr[0] if lr else {})


class ApproveTripView(SingleObjectMixin, View):
    model = models.Trip

    def post(self, request, *args, **kwargs):
        postdata = json.loads(self.request.body)
        trip = self.get_object()
        trip.chair_approved = bool(postdata.get('approved'))
        trip.save()
        return JsonResponse({'approved': trip.chair_approved})

    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        if not perm_utils.is_chair(request.user, trip.activity, False):
            return JsonResponse({}, status=403)
        return super().dispatch(request, *args, **kwargs)


class UserView(DetailView):
    model = models.User

    def get_queryset(self, *args, **kwargs):
        queryset = super().get_queryset(*args, **kwargs)
        if not perm_utils.is_leader(self.request.user):
            return queryset.filter(pk=self.request.user.id)
        return queryset

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class UserMembershipView(UserView):
    """ Fetch the user's membership information.

    By default, this checks the gear database for the most current information,
    but the `try_cache` query arg can be passed to first consult the cache
    instead.
    """
    def get(self, request, *args, **kwargs):
        user = self.get_object()
        try_cache = bool(request.GET.get('try_cache'))
        membership = geardb_utils.user_membership_expiration(user, try_cache)
        return JsonResponse(membership)


class UserRentalsView(UserView):
    def get(self, request, *args, **kwargs):
        user = self.get_object()
        return JsonResponse({'rentals': geardb_utils.user_rentals(user)})


class JWTView(View):
    """ Superclass for views that use JWT's for auth & signed payloads. """

    def dispatch(self, request, *args, **kwargs):
        """ Verify & decode JWT, storing its payload. """
        try:
            token = jwt_token_from_headers(request)
        except ValueError:
            return JsonResponse({'message': 'token missing'}, status=401)

        secret = settings.MEMBERSHIP_SECRET_KEY
        try:
            self.payload = jwt.decode(token, secret)
        except (jwt.exceptions.InvalidTokenError, KeyError):
            return JsonResponse({'message': 'invalid token'}, status=401)

        return super().dispatch(request, *args, **kwargs)


class UpdateMembershipView(JWTView):
    def post(self, request, *args, **kwargs):
        """ Receive a message that the user's membership was updated. """

        participant = models.Participant.from_email(self.payload['email'])
        if not participant:  # Not in our system, nothing to do
            return JsonResponse()

        keys = ('membership_expires', 'waiver_expires')
        update_fields = {key: date_from_iso(self.payload[key]) for key in keys
                         if self.payload.get(key)}
        membership, created = participant.update_membership(**update_fields)

        return JsonResponse({}, status=201 if created else 200)


class OtherVerifiedEmailsView(JWTView):
    def get(self, request, *args, **kwargs):
        """ Return any other verified emails that tie to the same user. """

        email = self.payload['email']

        addr = EmailAddress.objects.filter(email=email, verified=True).first()
        if not addr:  # Not in our system, so just return the original
            return JsonResponse({'primary': email, 'emails': [email]})

        # Normal case: Email is verified. Return all other verified emails
        verifed_emails = addr.user.emailaddress_set.filter(verified=True)
        return JsonResponse({
            'primary': addr.user.email,
            'emails': list(verifed_emails.values_list('email', flat=True))
        })


class MembershipStatusesView(View):
    def post(self, request, *args, **kwargs):
        """ Return a mapping of participant IDs to membership statuses. """
        postdata = json.loads(self.request.body)
        par_pks = postdata.get('participant_ids')
        if not isinstance(par_pks, list):
            return JsonResponse({'message': 'Bad request'}, status=400)

        # Span databases to map from participants -> users -> email addresses
        participants = models.Participant.objects.filter(pk__in=par_pks)
        user_to_par = dict(participants.values_list('user_id', 'pk'))
        email_addresses = EmailAddress.objects.filter(user_id__in=user_to_par, verified=True)
        email_to_user = dict(email_addresses.values_list('email', 'user_id'))

        # Gives email -> membership info for all matches
        matches = geardb_utils.matching_memberships(email_to_user)

        # Default to blank memberships in case not found
        no_membership = geardb_utils.repr_blank_membership()
        participant_memberships = {pk: no_membership for pk in par_pks}

        # Update participants where matching membership information was found
        for email, membership in matches.items():
            par_pk = user_to_par[email_to_user[email]]
            # We might overwrite a previous membership record, but that will
            # only happen if the user has memberships under 2+ emails
            # (Older memberships come first, so this will safely yield the newest)
            participant_memberships[par_pk] = membership

        return JsonResponse({'memberships': participant_memberships})

    def dispatch(self, request, *args, **kwargs):
        if not perm_utils.is_leader(request.user):
            return JsonResponse({}, status=403)
        return super().dispatch(request, *args, **kwargs)


class CheckTripOverflowView(View, SingleObjectMixin):
    """ JSON-returning view to be used for AJAX on trip editing. """
    model = models.Trip
    clear_response = {"msg": "",  # Returned message
                      "msg_type": ""}  # CSS class to apply

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

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


class TripsByLeaderView(View):
    def get(self, request, *args, **kwargs):
        by_leader = models.Participant.leaders.prefetch_related('trips_led')

        ret = [{
            'pk': leader.pk,
            'name': leader.name,
            'trips': [
                {'trip_date': trip.trip_date,
                 'activity': trip.get_activity_display(),
                 'name': trip.name,
                 } for trip in leader.trips_led.all()
            ],
        } for leader in by_leader]

        def leader_sort(leader):
            return (len(leader['trips']), leader['name'])
        most_trips_first = sorted(ret, key=leader_sort, reverse=True)

        return JsonResponse({'leaders': most_trips_first})
