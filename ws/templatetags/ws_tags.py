from django import template
from django.forms import HiddenInput
from ws.forms import AttendedLecturesForm
from ws.utils.dates import ws_year

register = template.Library()


@register.inclusion_tag('for_templatetags/lecture_attendance.html')
def lecture_attendance(participant, user_viewing, can_set_attendance=False):
    """ Show the participant's record for Winter School lecture attendance.

    If allowed, let the user change said participant's attendance.
    Cases where we allow this:
     - The activity chair marks them manually as having attended
     - The user marks themselves during the allowed window
    """
    attendance = participant.lectureattendance_set
    this_year = ws_year()
    form = AttendedLecturesForm(initial={'participant': participant})
    form.fields['participant'].widget = HiddenInput()  # Will be checked by view
    return {
        'form': form,
        'participant': participant,
        'user_viewing': user_viewing,
        'attended_lectures': attendance.filter(year=this_year).exists(),
        'past_attendance': attendance.exclude(year=this_year),
        'can_set_attendance': can_set_attendance,
    }
