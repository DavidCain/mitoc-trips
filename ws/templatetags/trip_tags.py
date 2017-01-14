from django import template

import ws.utils.ratings as ratings_utils

register = template.Library()


@register.inclusion_tag('for_templatetags/simple_trip_list.html')
def simple_trip_list(trip_list, max_title_chars=45, max_description_chars=120,
                     collapse_date=False):
    return {'trip_list': trip_list,
            'max_title_chars': max_title_chars,
            'max_description_chars': max_description_chars,
            'collapse_date': collapse_date}


@register.inclusion_tag('for_templatetags/trip_list_table.html')
def trip_list_table(trip_list):
    return {'trip_list': trip_list}


@register.inclusion_tag('for_templatetags/feedback_table.html')
def feedback_table(all_feedback):
    return {'all_feedback': all_feedback}


@register.filter
def name_with_rating(leader, trip):
    """ Give the leader's name plus rating at the time of the trip. """
    return leader.name_with_rating(trip)


@register.filter
def activity_rating(leader, activity):
    return leader.activity_rating(activity) or ""


@register.filter
def pending_applications_count(chair, activity, just_this_year=True):
    """ Count applications where:

    - All chairs have given recs, rating is needed
    - Viewing user hasn't given a rec
    """
    manager = ratings_utils.ApplicationManager(chair=chair, activity=activity)
    return len(manager.pending_applications(just_this_year))
