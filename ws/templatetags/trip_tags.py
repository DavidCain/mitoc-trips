import enum
from collections.abc import Collection
from datetime import timedelta
from typing import TYPE_CHECKING, Any, TypedDict

from django import template
from django.contrib.auth.models import User
from django.db.models import Case, Count, IntegerField, QuerySet, Sum, When

import ws.utils.dates as date_utils
import ws.utils.perms as perm_utils
import ws.utils.ratings as ratings_utils
from ws import enums, icons, models
from ws.utils.feedback import feedback_cutoff

register = template.Library()


class TripListAnnotations(TypedDict):
    num_signups: int
    signups_on_trip: int


if TYPE_CHECKING:
    from django_stubs_ext import WithAnnotations

    AnnotatedTrip = WithAnnotations[models.Trip, TripListAnnotations]
else:
    AnnotatedTrip = object


class TripStage(enum.IntEnum):
    FCFS_OPEN = 1
    LOTTERY_OPEN = 2
    NOT_YET_OPEN = 3
    FULL_BUT_ACCEPTING_SIGNUPS = 4
    CLOSED = 5

    def label(self) -> str:
        return {
            self.FCFS_OPEN: "Open",
            self.LOTTERY_OPEN: "Lottery",
            self.NOT_YET_OPEN: "Open soon",
            self.FULL_BUT_ACCEPTING_SIGNUPS: "Full",
            self.CLOSED: "Closed",
        }[self]

    def message_level(self) -> str:
        return {
            self.FCFS_OPEN: "success",
            self.LOTTERY_OPEN: "primary",
            self.NOT_YET_OPEN: "info",
            self.FULL_BUT_ACCEPTING_SIGNUPS: "warning",
            self.CLOSED: "default",
        }[self]

    def explanation(self) -> str:
        return {
            self.FCFS_OPEN: "Signups are accepted on a first-come, first-serve basis",
            self.LOTTERY_OPEN: "Signups are being accepted and participants will be assigned via lottery.",
            self.NOT_YET_OPEN: "Not yet accepting signups",
            self.FULL_BUT_ACCEPTING_SIGNUPS: "Trip has no more spaces, but you can join the waitlist",
            self.CLOSED: "No longer accepting signups",
        }[self]

    @classmethod
    def stage_for_trip(
        cls,
        trip: models.Trip,
        signups_on_trip: int,
    ) -> "TripStage":
        if trip.signups_not_yet_open:
            return cls.NOT_YET_OPEN
        if trip.signups_closed:
            return cls.CLOSED

        # All trips should be either open, closed, or not yet open.
        assert trip.signups_open, "Unexpected trip status!"

        if trip.algorithm == "fcfs":
            # `trip.open_slots` works, but includes a SQL query
            if signups_on_trip >= trip.maximum_participants:
                return cls.FULL_BUT_ACCEPTING_SIGNUPS
            return cls.FCFS_OPEN

        assert trip.algorithm == "lottery"
        return cls.LOTTERY_OPEN


@register.simple_tag
def trip_icon(trip):
    return icons.for_trip(trip)


def annotated_for_trip_list(trips: QuerySet[models.Trip]) -> QuerySet[AnnotatedTrip]:
    """Modify a trips queryset to have annotated fields used in tags."""
    # Each trip will need information about its leaders, so prefetch models
    trips = trips.prefetch_related("leaders", "leaders__leaderrating_set")

    # Django 2.0: Use conditional aggregation instead!
    signup_on_trip = Case(
        When(signup__on_trip=True, then=1), default=0, output_field=IntegerField()
    )
    return trips.annotate(
        num_signups=Count("signup"),
        signups_on_trip=Sum(signup_on_trip),
    )


@register.inclusion_tag("for_templatetags/simple_trip_list.html")
def simple_trip_list(
    trip_list: list[models.Trip],
    max_title_chars: int = 45,
    collapse_date: bool = False,  # True: Instead of showing the date column, show beneath title
) -> dict[str, Any]:
    return {
        "today": date_utils.local_date(),
        "trip_list": trip_list,
        "max_title_chars": max_title_chars,
        "collapse_date": collapse_date,
    }


@register.inclusion_tag("for_templatetags/trip_list_table.html")
def trip_list_table(
    trip_list: list[models.Trip],
    approve_mode: bool = False,
    show_trip_stage: bool = False,
) -> dict[str, Any]:
    return {
        "trip_list": trip_list,
        "approve_mode": approve_mode,
        "show_trip_stage": show_trip_stage,
    }


@register.inclusion_tag("for_templatetags/trip_stage.html")
def trip_stage(
    trip: models.Trip,
    signups_on_trip: int,
) -> dict[str, Any]:
    return {"stage": TripStage.stage_for_trip(trip, signups_on_trip)}


@register.filter
def numeric_trip_stage_for_sorting(
    trip: models.Trip,
    signups_on_trip: int,
) -> int:
    return TripStage.stage_for_trip(trip, signups_on_trip).value


@register.inclusion_tag("for_templatetags/feedback_table.html")
def feedback_table(
    all_feedback: Collection[models.Feedback],
    scramble_contents: bool = False,
    display_log_notice: bool = False,
    has_old_feedback: bool = False,
) -> dict[str, Any]:
    cutoff = feedback_cutoff()
    showing_old_feedback = any(
        feedback.time_created < cutoff for feedback in all_feedback
    )
    return {
        "all_feedback": all_feedback,
        "scramble_contents": scramble_contents,
        "display_log_notice": display_log_notice,
        "has_old_feedback": has_old_feedback,
        "showing_old_feedback": showing_old_feedback,
        "feedback_cutoff": cutoff.date(),
    }


@register.filter
def name_with_rating(leader: models.Participant, trip: models.Trip) -> str:
    """Give the leader's name plus rating at the time of the trip."""
    return leader.name_with_rating(trip)


@register.filter
def leader_display(feedback: models.Feedback) -> str:
    """Give a relevant display of the leader for display alongside feedback."""
    if feedback.trip:
        return feedback.leader.name_with_rating(feedback.trip)
    return feedback.leader.name


@register.filter
def activity_rating(leader: models.Participant, activity_enum: enums.Activity) -> str:
    return leader.activity_rating(activity_enum) or ""


@register.filter
def pending_applications_count(
    chair: models.Participant,
    activity_enum: enums.Activity,
) -> int:
    """Count applications where:

    - All chairs have given recs, rating is needed
    - Viewing user hasn't given a rec
    """
    manager = ratings_utils.ApplicationManager(chair=chair, activity_enum=activity_enum)
    return len(manager.pending_applications())


@register.filter
def unapproved_trip_count(activity_enum):
    today = date_utils.local_date()
    # TODO: Migrate away from legacy activity
    return models.Trip.objects.filter(
        trip_date__gte=today, activity=activity_enum.value, chair_approved=False
    ).count()


@register.inclusion_tag("for_templatetags/wimp_toolbar.html")
def wimp_toolbar(trip):
    return {"trip": trip}


@register.inclusion_tag("for_templatetags/trip_edit_buttons.html")
def trip_edit_buttons(
    trip: models.Trip,
    participant: models.Participant,
    user: User,
    hide_approve: bool = False,
) -> dict[str, Any]:
    available_at = date_utils.itinerary_available_at(trip.trip_date)

    required_activity = trip.required_activity_enum()
    last_approval = (
        (
            models.ChairApproval.objects.filter(trip_id=trip.pk)
            .select_related("approver")
            .order_by("pk")
            .last()
        )
        if required_activity and not hide_approve
        else None
    )

    # If there's no activity chair possible, hide approval (even from superusers!)
    if required_activity is None:
        hide_approve = True

    return {
        "trip": trip,
        "required_activity": required_activity,
        "is_chair": perm_utils.chair_or_admin(user, required_activity),
        "is_creator": trip.creator == participant,
        "is_trip_leader": perm_utils.leader_on_trip(participant, trip, False),
        "hide_approve": hide_approve,  # Hide approval even if user is a chair
        "last_approval": last_approval,
        "itinerary_available_at": available_at,
        "available_today": available_at.date() == date_utils.local_date(),
        "info_form_available": date_utils.local_now() >= available_at,
    }


@register.inclusion_tag("for_templatetags/view_trip.html")
def view_trip(
    trip: models.Trip,  # Should select `info`, prefetch `leaders` & `leaders__leaderrating_set`
    participant: models.Participant,
    user: User,
) -> dict[str, Any]:
    trip_leaders = trip.leaders.all()
    leader_signups = models.LeaderSignUp.objects.filter(trip=trip).select_related(
        "participant", "participant__lotteryinfo", "trip"
    )
    signups = models.SignUp.objects.filter(trip=trip).select_related(
        "participant", "participant__lotteryinfo", "trip"
    )
    wl_signups = trip.waitlist.signups.select_related(
        "participant", "participant__lotteryinfo"
    )
    return {
        "trip": trip,
        "is_trip_leader": perm_utils.leader_on_trip(participant, trip),
        "viewing_participant": participant,
        "user": user,
        "has_notes": (
            bool(trip.notes)
            or any(s.notes for s in signups)
            or any(s.notes for s in leader_signups)
        ),
        "signups": {
            "waitlist": wl_signups,
            "off_trip": signups.filter(on_trip=False).exclude(pk__in=wl_signups),
            "on_trip": signups.filter(on_trip=True),
            "leaders_on_trip": [
                s for s in leader_signups if s.participant in trip_leaders
            ],
            "leaders_off_trip": [
                s for s in leader_signups if s.participant not in trip_leaders
            ],
        },
        "par_signup": signups.filter(participant=participant).first(),
    }


@register.inclusion_tag("for_templatetags/wimp_trips.html")
def wimp_trips(participant, user):
    """Give a quick list of the trips that the participant is a WIMP for."""
    today = date_utils.local_date()
    next_week = today + timedelta(days=7)
    # Use Python to avoid an extra query into groups
    wimp_all = any(g.name == "WIMP" for g in user.groups.all())

    all_wimp_trips = models.Trip.objects if wimp_all else participant.wimp_trips
    upcoming_trips = all_wimp_trips.filter(
        trip_date__gte=today, trip_date__lte=next_week
    )
    upcoming_trips = upcoming_trips.select_related("info")

    return {
        "can_wimp_all_trips": wimp_all,
        "upcoming_trips": upcoming_trips.order_by("trip_date", "name"),
    }
