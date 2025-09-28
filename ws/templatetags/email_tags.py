from typing import Any

from allauth.account.models import EmailAddress
from django import template
from django.db.models import QuerySet

from ws import enums, models

register = template.Library()


@register.filter
def has_unverified_email(emails: QuerySet[EmailAddress]) -> bool:
    return any(not email.verified for email in emails)


def _conditional_rendering(trip: models.Trip) -> dict[str, bool]:
    return {
        "show_program": trip.program_enum != enums.Program.NONE,
        "show_trip_type": trip.trip_type_enum != enums.TripType.NONE,
    }


@register.inclusion_tag("for_templatetags/email/upcoming_trip_summary.txt")
def upcoming_trip_summary_txt(trip):
    """Summarize an upcoming trip in textual format.

    Trip should be annotated to have `signups_on_trip`
    """
    return {
        "trip": trip,
        "underline_trip_name": "=" * len(trip.name),
        **_conditional_rendering(trip),
    }


@register.inclusion_tag("for_templatetags/email/upcoming_trip_summary.html")
def upcoming_trip_summary_html(trip):
    """Summarize an upcoming trip in HTML format.

    Trip should be annotated to have `signups_on_trip`
    """
    return {"trip": trip, **_conditional_rendering(trip)}


@register.inclusion_tag("for_templatetags/email/trip_needing_approval.html")
def trip_needing_approval(
    activity_enum: enums.Activity, trip: models.Trip
) -> dict[str, Any]:
    return {"trip": trip, "activity_enum": activity_enum}
