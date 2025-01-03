import json
from collections.abc import Collection, Iterable, Iterator
from datetime import date
from typing import Any, TypedDict, cast
from zoneinfo import ZoneInfo

import jwt
import jwt.exceptions
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q, QuerySet
from django.http import HttpRequest, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import DetailView, ListView, View
from django.views.generic.detail import SingleObjectMixin
from typing_extensions import NotRequired

import ws.utils.geardb as geardb_utils
import ws.utils.membership as membership_utils
import ws.utils.perms as perm_utils
import ws.utils.signups as signup_utils
from ws import enums, models
from ws.decorators import group_required
from ws.middleware import RequestWithParticipant
from ws.mixins import JsonTripLeadersOnlyView
from ws.utils import membership_api
from ws.utils.api import jwt_token_from_headers
from ws.utils.feedback import feedback_is_recent
from ws.utils.member_stats import (
    CacheStrategy,
    MembershipInformation,
    fetch_membership_information,
)


class SimpleSignupsView(DetailView):
    """Give the name and email of leaders and signed up participants."""

    model = models.Trip

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        trip = self.get_object()

        on_trip = trip.signed_up_participants.filter(signup__on_trip=True)
        signups = {
            "onTrip": on_trip.values("name", "email"),
            "waitlist": [
                {"name": s.participant.name, "email": s.participant.email}
                for s in trip.waitlist.signups.select_related("participant")
            ],
        }

        return JsonResponse(
            {
                "signups": {
                    key: [{"participant": par} for par in participants]
                    for key, participants in signups.items()
                },
                "leaders": list(trip.leaders.values("name", "email")),
                "creator": {"name": trip.creator.name, "email": trip.creator.email},
            }
        )

    def dispatch(self, request, *args, **kwargs):
        """Participant object must exist, but it need not be current."""
        if not self.request.participant:
            return JsonResponse({}, status=403)
        return super().dispatch(request, *args, **kwargs)


class FormatSignupMixin:
    request: HttpRequest

    def describe_signup(
        self,
        signup: models.SignUp,
        trip_participants: Collection[models.Participant],
        other_trips: Iterable[models.Trip],
    ) -> dict[str, Any]:
        """Yield everything used in the participant-selecting modal.

        The signup object should come with related models already selected,
        or this could result in a _lot_ of extra queries.

        :param signup: An models.SignUp instance (either on trip or waitlisted)
        :param trip_participants: All Participants that are on the same trip
        :param other_trips: Other trips they're on this weekend(ish)
        """
        par = signup.participant

        # Normally, we could annotate the class request as RequestWithParticipant.
        # However, annotating that contradicts the parent class. Just cast.
        viewing_participant = cast(RequestWithParticipant, self.request).participant
        feedback = (
            []
            # In rare cases, a trip creator can be a participant on their own trip.
            # Be sure we hide feedback from them if this is the case.
            if signup.participant == viewing_participant
            # Filter in Python, since this is prefetched
            else [f for f in par.feedback_set.all() if feedback_is_recent(f)]
        )

        try:
            lotteryinfo = par.lotteryinfo
        except models.LotteryInfo.DoesNotExist:
            lotteryinfo = None

        num_passengers = lotteryinfo and lotteryinfo.number_of_passengers

        # Show 'paired with' only if that user is also on the trip
        paired_with = lotteryinfo and lotteryinfo.reciprocally_paired_with
        if paired_with not in trip_participants:  # Includes waitlist!
            paired_with = None

        return {
            "id": signup.id,
            "participant": {"id": par.id, "name": par.name, "email": par.email},
            "missed_lectures": par.missed_lectures_for(signup.trip),
            "feedback": [
                {
                    "showed_up": f.showed_up,
                    "leader": f.leader.name,
                    "comments": f.comments,
                    "trip": {"id": f.trip.id, "name": f.trip.name},
                }
                for f in feedback
            ],
            "also_on": [{"id": trip.pk, "name": trip.name} for trip in other_trips],
            "paired_with": (
                {"id": paired_with.pk, "name": paired_with.name}
                if paired_with
                else None
            ),
            "car_status": lotteryinfo and lotteryinfo.car_status,
            "number_of_passengers": num_passengers,
            "notes": signup.notes,
        }


class SignupsChangedError(Exception):
    """An exception to be raised when a trip's signups have changed.

    If a particular signup wasn't known to be on the trip when loading trip
    data, race conditions could arise. The leader may later request some trip
    modifications (based off their stale data), and we don't define a way of
    dealing with that unknown signup. This exception should then be raised.
    """


class JsonSignup(TypedDict):
    id: int
    deleted: NotRequired["bool"]


class AdminTripSignupsView(
    SingleObjectMixin, FormatSignupMixin, JsonTripLeadersOnlyView
):
    model = models.Trip

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        return JsonResponse(self.describe_all_signups())

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        """Take a list of exactly how signups should be ordered and apply it.

        To avoid dealing with concurrency, calculating diffs, etc. we just
        assume that the leader posting these changes has the authoritative say
        on who gets to be on the trip, and in what order.

        There are some basic checks in place to stop them from making
        modifications after the trip substantially changes (e.g. new
        participants sign up, but they don't see that). Otherwise, though,
        their ordering overrides any other.
        """
        trip = self.object = self.get_object()

        postdata = json.loads(self.request.body)  # TODO: assumes valid JSON.
        signup_list: list[JsonSignup] = postdata.get("signups", [])
        maximum_participants: int | None = postdata.get("maximum_participants")

        def error(msg: str) -> JsonResponse:
            return JsonResponse({"message": msg}, status=400)

        # Any non-validation errors will trigger rollback
        with transaction.atomic():
            try:
                self.update(trip, signup_list, maximum_participants)
            except ValidationError:
                return error(f"Couldn't change trip size to {maximum_participants}")
            except SignupsChangedError:
                return error(
                    "Signups were recently added or removed. "
                    "Unable to modify trip without current data."
                )
            return JsonResponse({})

    def update(
        self,
        trip: models.Trip,
        signup_list: list[JsonSignup],
        maximum_participants: int | None,
    ) -> None:
        """Take parsed input data and apply the changes."""
        if maximum_participants:
            trip.maximum_participants = maximum_participants
            trip.full_clean()  # Raises ValidationError
            trip.save()
        # Anything already on should be waitlisted
        self.update_signups(signup_list, trip)

    @staticmethod
    def signups_to_update(
        signup_list: list[JsonSignup],
        trip: models.Trip,
    ) -> tuple[QuerySet[models.SignUp], QuerySet[models.SignUp]]:
        """From the payload, break signups into deletion & those that stay.

        All signups are given (in order) in `signup_list`. If the `deleted` key
        is true, then we should remove the signup. Otherwise, we'll add signups
        in order. This method breaks the signups into two groups: those that
        need to be added to the trip in order, and those that must be removed.
        """
        # Handle weird edge cases: new signup was created
        if trip.on_trip_or_waitlisted.count() != len(signup_list):
            raise SignupsChangedError("There are signups not included in the request")

        deletions = [s["id"] for s in signup_list if s.get("deleted")]
        normal_signups = [s["id"] for s in signup_list if not s.get("deleted")]

        # Use raw SQL to maintain the original list order in our QuerySet
        ordering = " ".join(
            f"when ws_signup.id={pk} then {i}" for i, pk in enumerate(normal_signups)
        )

        # Return unevaluated QuerySet objects (allows update() and all() calls)
        keep_on_trip = (
            trip.signup_set.filter(pk__in=normal_signups)
            .extra(  # noqa: S610
                select={"ordering": f"case {ordering} end"},
                order_by=("ordering",),
            )
            .select_related("waitlistsignup")
        )
        to_delete = trip.signup_set.filter(pk__in=deletions)

        if keep_on_trip.count() != len(normal_signups):
            raise ValidationError("At least one passed ID no longer exists!")

        return (keep_on_trip, to_delete)

    def update_signups(self, signup_list: list[JsonSignup], trip: models.Trip) -> None:
        """Mark all signups as not on trip, then add signups in order."""
        keep_on_trip, to_delete = self.signups_to_update(signup_list, trip)

        # Clear the trip first (delete removals, set others to not on trip)
        # Both methods (update and skip_signals) ignore waitlist-bumping
        keep_on_trip.update(on_trip=False)
        for kill_signup in to_delete:
            # Setting properties dynamically on an object is a huge anti-pattern.
            # *Almost* as bad as using Django signals in the first place...
            # Hopefully we change this at a later date.
            kill_signup.skip_signals = True  # type: ignore[attr-defined]
            kill_signup.delete()

        # `all()` hits the db, will fetch current (`on_trip=False`) signups
        ordered_signups = keep_on_trip.all()

        for order, signup in enumerate(ordered_signups):
            signup_utils.trip_or_wait(signup, trip_must_be_open=False)
            signup_utils.next_in_order(signup, order)

    def get_signups(self) -> QuerySet[models.SignUp]:
        """Trip signups with selected models for use in describe_signup.

        Unlike in normal Django template uses, this method reports signups that
        are on the trip in the same collection as signups which represent a
        spot on the waitlist.
        """
        trip: models.Trip = self.get_object()
        return (
            trip.on_trip_or_waitlisted.select_related(
                "participant",
                "participant__lotteryinfo__paired_with__lotteryinfo",
            )
            .prefetch_related(
                # Older feedback should still be filtered out
                "participant__feedback_set",
                "participant__feedback_set__leader",
                "participant__feedback_set__trip",
            )
            .order_by(
                "-on_trip",
                F("waitlistsignup__manual_order").desc(nulls_last=True),
                F("waitlistsignup__time_created").asc(),
                "last_updated",
            )
        )

    def describe_all_signups(self) -> dict[str, Any]:
        """Get information about the trip's signups."""
        trip = self.get_object()
        signups = self.get_signups()
        trip_participants = {s.participant for s in signups}

        other_trips_by_par = dict(trip.other_trips_by_participant())

        return {
            "signups": [
                self.describe_signup(
                    s, trip_participants, other_trips_by_par[s.participant_id]
                )
                for s in signups
            ],
            "leaders": list(trip.leaders.values("name", "email")),
            "creator": {"name": trip.creator.name, "email": trip.creator.email},
        }


class LeaderParticipantSignupView(
    SingleObjectMixin, FormatSignupMixin, JsonTripLeadersOnlyView
):
    model = models.Trip

    def post(self, request, *args, **kwargs):
        """Process the participant & trip, create or update signup as needed.

        This method handles two main cases:
        - Participant has never signed up for the trip, will be placed
        - Participant has signed up before, but is not on the trip
        """
        postdata = json.loads(self.request.body)
        par_pk = postdata.get("participant_id")
        notes = postdata.get("notes", "")

        try:
            par = models.Participant.objects.get(pk=par_pk)
        except models.Participant.DoesNotExist:
            return JsonResponse({"message": "No participant found"}, status=404)

        trip = self.get_object()
        signup, created = models.SignUp.objects.get_or_create(
            trip=trip, participant=par, defaults={"notes": notes}
        )

        if not created:  # (SignUp exists, but participant may not be on trip)
            try:
                already_on_trip = signup.on_trip or signup.waitlistsignup
            except models.WaitListSignup.DoesNotExist:
                already_on_trip = False

            if already_on_trip:
                queue = "trip" if signup.on_trip else "waitlist"
                return JsonResponse(
                    {"message": f"{par.name} is already on the {queue}"}, status=409
                )

        signup = signup_utils.trip_or_wait(signup)

        trip_participants = {
            s.participant
            for s in trip.on_trip_or_waitlisted.select_related("participant")
        }

        other_trips_by_par = dict(
            trip.other_trips_by_participant(for_participants=[par])
        )
        other_trips = other_trips_by_par[par.pk]

        # signup: descriptor, agnostic of presence on the trip or waiting list
        # on_trip: a boolean to place this signup in the right place
        #          (either at the bottom of the trip list or waiting list)
        return JsonResponse(
            {
                "signup": self.describe_signup(signup, trip_participants, other_trips),
                "on_trip": signup.on_trip,
            },
            status=201 if (created or signup.on_trip) else 200,
        )


class JsonParticipantsView(ListView):
    model = models.Participant

    def top_matches(self, search=None, exclude_self=False, max_results=20):
        participants = self.get_queryset()
        if search:
            # This search is not indexed, or particularly advanced
            # TODO: Use Postgres FTS, either in raw SQL or through ORM
            # (Django 1.10 introduces support for full-text search)
            match = Q(name__icontains=search) | Q(email__icontains=search)
            participants = participants.filter(match)
        if exclude_self:
            participants = participants.exclude(pk=self.request.participant.pk)

        yield from self._serialize_participants(participants[:max_results])

    def from_pk(self, participant_ids):
        participants = self.get_queryset().filter(pk__in=participant_ids)
        yield from self._serialize_participants(participants)

    @staticmethod
    def _serialize_participants(participants):
        for participant in participants:
            yield {
                "id": participant.pk,
                "name": participant.name,
                "email": participant.email,
                "avatar": participant.avatar_url(100),
            }

    def render_to_response(self, context, **response_kwargs):
        participant_ids = self.request.GET.getlist("id")
        if participant_ids:
            matches = self.from_pk(participant_ids)
        else:
            search = self.request.GET.get("search")
            exclude_self = bool(self.request.GET.get("exclude_self"))
            matches = self.top_matches(search, exclude_self)

        return JsonResponse({"participants": list(matches)})

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        """Participant object must exist, but it need not be current."""
        if not self.request.participant:
            return JsonResponse({}, status=403)
        return super().dispatch(request, *args, **kwargs)


class JsonProgramLeadersView(View):
    """Give basic information about leaders for a program."""

    @staticmethod
    def describe_leaders(program_enum):
        activity_enum = program_enum.required_activity()

        leaders = models.LeaderRating.objects.filter(active=True)
        if activity_enum:
            leaders = leaders.filter(activity=activity_enum.value)

        ratings = (
            leaders.select_related("participant")
            # (If there are duplicates activity ratings for an activity, just take most recent)
            # (If we have an open program, the leader may have multiple ratings -- just pick one)
            .order_by("participant__id", "-time_created")
            .distinct("participant_id")
        )

        for rating in ratings:
            yield {
                "id": rating.participant.pk,
                "name": rating.participant.name,
                "rating": rating.rating if activity_enum else None,
            }

    def get(self, context, **response_kwargs):
        try:
            program_enum = enums.Program(self.kwargs["program"])
        except ValueError:
            return JsonResponse({}, status=404)

        return JsonResponse(
            {
                "leaders": sorted(
                    self.describe_leaders(program_enum), key=lambda par: par["name"]
                )
            }
        )

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


@login_required
def get_rating(request, pk, activity):
    query = Q(participant__pk=pk, activity=activity, active=True)
    lr = models.LeaderRating.objects.filter(query).values("rating", "notes")
    return JsonResponse(lr[0] if lr else {})


class ApproveTripView(SingleObjectMixin, View):
    model = models.Trip

    def post(self, request, *args, **kwargs):
        postdata = json.loads(self.request.body)
        trip = self.get_object()
        trip.chair_approved = bool(postdata.get("approved"))
        trip.save()
        return JsonResponse({"approved": trip.chair_approved})

    def dispatch(self, request, *args, **kwargs):
        trip = self.get_object()
        activity_enum = trip.required_activity_enum()
        if activity_enum is None:
            return JsonResponse(
                {"message": f"No chair for {trip.program_enum.label}"}, status=400
            )
        if not perm_utils.chair_or_admin(request.user, activity_enum):
            return JsonResponse({}, status=403)
        return super().dispatch(request, *args, **kwargs)


class UserView(DetailView):
    model = User

    def get_queryset(self):
        queryset = super().get_queryset()
        if not perm_utils.is_leader(self.request.user):
            return queryset.filter(pk=self.request.user.id)
        return queryset

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)


class UserMembershipView(UserView):
    """Fetch the user's dues and waiver information."""

    def get(self, request, *args, **kwargs):
        user = self.get_object()

        # TODO: Hitting the gear database *every time* is probably not necessary.
        # For most people, knowing that their dues & waiver are active is enough.
        # (We can rely on the membership cache to tell us if somebody's active)
        # Similarly, if mitoc-gear is down, falling back on the cache would be nice.

        # Almost all people hitting this endpoint will have completed registration.
        # In this case, use the opportunity to update the cache!
        participant = models.Participant.from_user(user)
        if participant:
            membership_utils.get_latest_membership(participant)
            return JsonResponse(membership_api.format_cached_membership(participant))

        return JsonResponse(
            membership_api.jsonify_membership_waiver(
                geardb_utils.query_geardb_for_membership(user)
            )
        )


class UserRentalsView(UserView):
    def get(self, request, *args, **kwargs):
        """Describe all items the user has checked out from MITOC."""
        user = self.get_object()
        rented_items = [
            # TODO: Could instead use a dataclass with an `as_dict()` invocation or a TypedDict
            {
                "email": r.email,
                "id": r.id,
                "name": r.name,
                "cost": r.cost,
                "checkedout": r.checkedout,
                "overdue": r.overdue,
            }
            for r in geardb_utils.user_rentals(user)
        ]
        return JsonResponse({"rentals": rented_items})


class JWTView(View):
    """Superclass for views that use JWT's for auth & signed payloads."""

    @method_decorator(csrf_exempt)
    def dispatch(self, request, *args, **kwargs):
        """Verify & decode JWT, storing its payload.

        Disable CSRF validation on these requests, since they will be
        all be cross-origin, and validation is done entirely by JWT.
        """
        try:
            token = jwt_token_from_headers(request)
        except ValueError:
            return JsonResponse({"message": "token missing"}, status=401)

        secret = settings.MEMBERSHIP_SECRET_KEY
        try:
            self.payload = jwt.decode(token, secret, algorithms=["HS512", "HS256"])
        except jwt.exceptions.InvalidAlgorithmError:
            return JsonResponse({"message": "invalid algorithm"}, status=401)
        except (jwt.exceptions.InvalidTokenError, KeyError):
            return JsonResponse({"message": "invalid token"}, status=401)

        return super().dispatch(request, *args, **kwargs)


class UpdateMembershipView(JWTView):
    def post(self, request, *args, **kwargs):
        """Receive a message that the user's dues and/or waiver were updated."""
        participant = models.Participant.from_email(self.payload["email"])
        if not participant:  # Not in our system, nothing to do
            return JsonResponse({})

        update_fields = {
            key: date.fromisoformat(self.payload[key])
            for key in ("membership_expires", "waiver_expires")
            if self.payload.get(key)
        }
        _membership, created = participant.update_membership(**update_fields)

        return JsonResponse({}, status=201 if created else 200)


class OtherVerifiedEmailsView(JWTView):
    def get(self, request, *args, **kwargs):
        """Return any other verified emails that tie to the same user."""
        email = self.payload["email"]

        addr = EmailAddress.objects.filter(email=email, verified=True).first()
        if not addr:  # Not in our system, so just return the original
            # This API endpoint is for trusted entities; it's okay to give a null name.
            # (in other words, there's no user enumeration vulnerability here)
            return JsonResponse({"name": None, "primary": email, "emails": [email]})

        # Normal case: Email is verified. Return all other verified emails
        verifed_emails = addr.user.emailaddress_set.filter(verified=True)
        participant = models.Participant.objects.filter(user=addr.user).first()
        return JsonResponse(
            {
                "name": participant and participant.name,
                "primary": addr.user.email,
                # No real reason to sort these, apart from making return order deterministic)
                "emails": sorted(verifed_emails.values_list("email", flat=True)),
            }
        )


class MembershipStatusesView(View):
    """Bulk fetch a number of participants' (cached) membership status.

    This view is used for leaders trying to make sure that all their trip
    participants are actually able to go on the trip.
    """

    def post(self, request, *args, **kwargs):
        """Return a mapping of participant IDs to dues/waiver statuses."""
        postdata = json.loads(self.request.body)
        par_pks = postdata.get("participant_ids")
        if not isinstance(par_pks, list):
            return JsonResponse({"message": "Bad request"}, status=400)

        return JsonResponse(
            {
                "memberships": {
                    participant.pk: membership_api.format_cached_membership(participant)
                    for participant in models.Participant.objects.filter(
                        pk__in=par_pks
                    ).select_related("membership")
                }
            }
        )

    def dispatch(self, request, *args, **kwargs):
        if not perm_utils.is_leader(request.user):
            return JsonResponse({}, status=403)
        return super().dispatch(request, *args, **kwargs)


class MemberInfo(TypedDict):
    email: str
    affiliation: str
    num_rentals: int
    # Only reported if they are an MIT student!
    mit_email: str | None
    # Fields from TripInformation, if found
    is_leader: NotRequired[bool]
    num_trips_attended: NotRequired[int]
    num_trips_led: NotRequired[int]


class RawMembershipStatsView(View):
    @staticmethod
    def _flat_members_info(
        members: list[MembershipInformation],
    ) -> Iterator[MemberInfo]:
        for info in members:
            flat_info: MemberInfo = {
                "email": info.email,
                "mit_email": info.mit_email,
                "affiliation": info.affiliation,
                "num_rentals": info.num_rentals,
            }

            if info.trips_information:
                flat_info.update(
                    # A bit repetetive, but `_as_dict()` won't satisfy mypy
                    {
                        "email": info.trips_information.email,
                        "is_leader": info.trips_information.is_leader,
                        "num_trips_attended": info.trips_information.num_trips_attended,
                        "num_trips_led": info.trips_information.num_trips_led,
                    }
                )
                # If there's a verified MIT email address from the trips site, use it!
                if info.trips_information.verified_mit_email is not None:
                    flat_info["mit_email"] = info.trips_information.verified_mit_email
            yield flat_info

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        cache_str = self.request.GET.get(
            "cache_strategy",
            CacheStrategy.FETCH_IF_STALE_ASYNC.value,  # "default"
        )
        try:
            cache_strategy = CacheStrategy(cache_str)
        except ValueError:
            valid_values = ", ".join(strat.value for strat in CacheStrategy)
            return JsonResponse(
                {"message": f"Cache strategy must be one of {valid_values}"},
                status=400,
            )

        stats = fetch_membership_information(cache_strategy)

        return JsonResponse(
            {
                "retrieved_at": stats.retrieved_at.astimezone(
                    ZoneInfo("America/New_York")
                ).isoformat(timespec="seconds"),
                "members": list(self._flat_members_info(stats.members)),
            }
        )

    @method_decorator(group_required("leaders"))
    def dispatch(self, request, *args, **kwargs):
        # TODO: Restrict to BOD only
        return super().dispatch(request, *args, **kwargs)
