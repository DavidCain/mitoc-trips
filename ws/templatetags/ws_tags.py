from typing import Any

from django import template
from django.forms import HiddenInput

from ws import models
from ws.forms import AttendedLecturesForm
from ws.utils.dates import ws_year

register = template.Library()


@register.inclusion_tag("for_templatetags/lecture_attendance.html")
def lecture_attendance(
    participant: models.Participant,
    user_viewing: bool,
    can_set_attendance: bool = False,
) -> dict[str, Any]:
    """Show the participant's record for Winter School lecture attendance.

    If allowed, let the user change said participant's attendance.
    Cases where we allow this:
     - The activity chair marks them manually as having attended
     - The user marks themselves during the allowed window
    """
    years = sorted(
        attendance.year for attendance in participant.lectureattendance_set.all()
    )
    max_year = years[-1] if years else None
    this_year = ws_year()
    form = AttendedLecturesForm(initial={"participant": participant})
    form.fields["participant"].widget = HiddenInput()  # Will be checked by view
    return {
        "form": form,
        "participant": participant,
        "user_viewing": user_viewing,
        "attended_lectures": max_year and max_year >= this_year,
        "lecture_year": max_year,
        "past_attendance": [year for year in years if year < this_year],
        "can_set_attendance": can_set_attendance,
    }
