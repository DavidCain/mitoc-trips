from django import template

register = template.Library()


@register.inclusion_tag('for_templatetags/email/upcoming_trip_summary.txt')
def upcoming_trip_summary_txt(trip):
    """ Summarize an upcoming trip in textual format.

    Trip should be annotated to have `signups_on_trip`
    """
    return {'trip': trip, 'underline_trip_name': '=' * len(trip.name)}


@register.inclusion_tag('for_templatetags/email/upcoming_trip_summary.html')
def upcoming_trip_summary_html(trip):
    """ Summarize an upcoming trip in HTML format.

    Trip should be annotated to have `signups_on_trip`
    """
    return {'trip': trip}
