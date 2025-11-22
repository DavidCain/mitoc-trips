import logging
from collections.abc import Iterator
from datetime import timedelta
from typing import NamedTuple

from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
from typing_extensions import assert_never

from ws import enums, models
from ws.utils import dates as date_utils

logger = logging.getLogger(__name__)


class ReminderIsSent(NamedTuple):
    activity_enum: enums.Activity
    has_trip_info: bool


def _upcoming_trips_lacking_approval(trips: list[models.Trip]) -> list[models.Trip]:
    today = date_utils.local_date()
    already_approved_trip_ids = {
        approval.trip_id
        for approval in models.ChairApproval.objects.filter(trip_id__in=trips)
    }
    return [
        trip
        for trip in trips
        # It's pointless to remind about trips in the past
        if trip.trip_date >= today
        # Obviously, approved trips ought be excluded
        and trip.id not in already_approved_trip_ids
        # Circuses & trips that have no activity should never need reminding
        # (we assume they got in by nature of a race condition)
        and trip.required_activity_enum() is not None
    ]


def _notified_chairs_too_recently(trips: list[models.Trip]) -> bool:
    now = date_utils.local_now()

    # Wait, why are multiple activities possible? (it's a weird edge case)
    # This method answers "should we notify one activity chair about these trips?"
    # We call the method with a collection of trip IDs meant for one chair;
    # they **all shared the same activity at the time they were inspected.**
    # However, if one trip changed activity in the small window between
    # fanning out trips to chairs based on activity & calling this method...
    # we still want to notify at least one chair about the trip, even
    # if the activity chair that we notify is the wrong one!
    # (we'll notify the new activity chair on the next pass)
    trip_activities: list[str] = []
    for trip in trips:
        activity_enum = trip.required_activity_enum()
        if activity_enum is not None:
            trip_activities.append(activity_enum.value)

    try:
        last_reminder_sent = models.ChairApprovalReminder.objects.filter(
            activity__in=trip_activities
        ).latest("pk")
    except models.ChairApprovalReminder.DoesNotExist:
        pass
    else:
        if last_reminder_sent.time_created > (now - timedelta(minutes=55)):
            logger.error(
                "Trying to send another reminder for %s trips at %s, less than an hour since last reminder email at %s",
                ", ".join(trip_activities),
                now,
                last_reminder_sent.time_created,
            )
            return True
    return False


def _trips_without_similar_reminders(
    trips: list[models.Trip],
) -> Iterator[tuple[models.Trip, str]]:
    """Identify trips which have not already been sent to chairs in their current state.

    We can regard a trip as having been notified if both:
    1. An email was sent containing that trip in the message.
    2. The activity & itinerary (at the time the email was sent) match current values.
    """
    reminders_sent_per_trip: dict[models.Trip, list[ReminderIsSent]] = {}

    def _get_reminder_key(trip: models.Trip) -> ReminderIsSent:
        activity_enum = trip.required_activity_enum()
        assert activity_enum is not None, f"Trip #{trip.id} somehow has no activity?"
        return ReminderIsSent(activity_enum, trip.info_id is not None)

    for reminder in models.ChairApprovalReminder.objects.filter(
        trip_id__in=trips
    ).select_related("trip"):
        reminders_sent_per_trip.setdefault(reminder.trip, []).append(
            ReminderIsSent(enums.Activity(reminder.activity), reminder.had_trip_info)
        )

    for trip in trips:
        # We do *not* want to prompt for "hey, approve these trips!" before itineraries are available.
        # 1. It encourages the wrong behavior (approving trips too early to silence emails).
        # 2. Trips are ideally meant to be approved once an itinerary is posted.
        if not trip.info_editable:
            continue
        reminders = reminders_sent_per_trip.get(trip, [])
        if not reminders:
            yield trip, "has not been sent to activity chairs"
        elif _get_reminder_key(trip) not in reminders:
            previously_reminded_activities = {
                reminder.activity_enum for reminder in reminders
            }
            if trip.required_activity_enum() not in previously_reminded_activities:
                yield (
                    trip,
                    # This should be exceptionally rare...
                    f"changed activities (a reminder was sent for {', '.join(sorted(activity.label for activity in previously_reminded_activities))})",
                )
            else:
                # Itineraries can only be edited, not deleted.
                yield trip, "now has an itinerary"


def reasons_to_remind_activity_chairs(trips: list[models.Trip]) -> list[str]:
    """Avoid sending reminder emails until actually necessary.

    This will return a non-empty list  *only* if:
    1. We should notify the chair in the first place about one or more trips.
    2. There would be something new in the email body were we to notify chairs
       about the trips needing approval.

    If we're already sending an email, we might as well notify them about
    *all* trips currently pending approval.
    """
    now = date_utils.local_now()
    if _notified_chairs_too_recently(trips):
        return []
    trips_lacking_approval = _upcoming_trips_lacking_approval(trips)

    # If *any* trips leave tomorrow & don't have an approval, remind!
    tomorrow = now.date() + timedelta(days=1)
    trips_leaving_soon = [
        f"trip #{trip.id} starts very soon (on {trip.trip_date}) but has no approval!"
        for trip in trips_lacking_approval
        if trip.trip_date <= tomorrow
    ]
    if trips_leaving_soon:
        return trips_leaving_soon

    return [
        f"trip #{trip.id} {reason}"
        for trip, reason in _trips_without_similar_reminders(trips_lacking_approval)
    ]


class ChairContact(NamedTuple):
    name: str
    email: str


def contacts_for_activity_chair(activity: enums.Activity) -> list[ChairContact]:
    if activity == enums.Activity.BIKING:
        return [ChairContact("mountain biking chair", "mtnbike-chair@mit.edu")]
    if activity == enums.Activity.BOATING:
        return [ChairContact("boathouse manager", "boathouse-mgr@mit.edu")]
    if activity == enums.Activity.CABIN:
        # 1) Cabin trips don't require approval
        # 2) We don't provide any way to indicate *which* cabin is being used.
        return [
            ChairContact("Camelot manager", "camelot-mgr@mit.edu"),
            ChairContact("Interval manager", "intervale-mgr@mit.edu"),
        ]
    if activity == enums.Activity.CLIMBING:
        return [ChairContact("climbing chair", "climbing-chair@mit.edu")]
    if activity == enums.Activity.HIKING:
        # Include 3-season chair for now, 3SSC is new
        return [
            ChairContact("3-season hiking chair", "3s-hiking-chair@mit.edu"),
            ChairContact("3-season Safety Committee", "mitoc-3ssc@mit.edu"),
        ]
    if activity == enums.Activity.WINTER_SCHOOL:
        # Exclude WS chairs, they don't approve trips.
        return [ChairContact("Winter Safety Committee", "mitoc-wsc@mit.edu")]
    assert_never(activity)


def notify_activity_chair(
    activity_enum: enums.Activity,
    trips: list[models.Trip],
    reasons_to_send: list[str],
) -> EmailMultiAlternatives:
    context = {
        "activity_enum": activity_enum,
        "trips": trips,
        "reasons_to_send": reasons_to_send,
    }

    text_content = (
        get_template("email/approval/trips_needing_approval.txt")
        .render(context)
        .strip()
    )
    html_content = get_template("email/approval/trips_needing_approval.html").render(
        context
    )

    msg = EmailMultiAlternatives(
        f"{len(trips)} {activity_enum.label} {'trip needs' if len(trips) == 1 else 'trips need'} approval",
        text_content,
        to=[contact.email for contact in contacts_for_activity_chair(activity_enum)],
        # TEMPORARY while we make sure this feature works as expected.
        cc=["djcain@mit.edu"],
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send()

    # Creating a record of the reminders is the mechanism by which we don't spam chairs.
    models.ChairApprovalReminder.objects.bulk_create(
        [
            models.ChairApprovalReminder(
                trip=trip,
                # Importantly, we log the receiving chair activity, *NOT* trip activity.
                # (this has ramifications for an edge case on trips changing activity)
                activity=activity_enum.value,
                had_trip_info=trip.info is not None,
            )
            for trip in trips
        ]
    )
    return msg
