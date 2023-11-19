from django import template

from ws import enums

register = template.Library()


def _conditional_rendering(trip):
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
