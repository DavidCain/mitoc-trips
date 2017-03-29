from django import template
from django.db.models import Case, Count, IntegerField, Sum, When

from ws import models

import ws.utils.dates as date_utils
import ws.utils.ratings as ratings_utils
import ws.utils.perms as perm_utils

register = template.Library()


def annotated_for_trip_list(trips):
    """ Modify a trips queryset to have annotated fields used in tags. """
    # Each trip will need information about its leaders, so prefetch models
    trips = trips.prefetch_related('leaders', 'leaders__leaderrating_set')

    signup_on_trip = Case(
        When(signup__on_trip=True, then=1),
        default=0,
        output_field=IntegerField()
    )
    return trips.annotate(num_signups=Count('signup'),
                          signups_on_trip=Sum(signup_on_trip))


@register.inclusion_tag('for_templatetags/simple_trip_list.html')
def simple_trip_list(trip_list, max_title_chars=45, max_description_chars=120,
                     collapse_date=False):
    return {'trip_list': trip_list,
            'max_title_chars': max_title_chars,
            'max_description_chars': max_description_chars,
            'collapse_date': collapse_date}


@register.inclusion_tag('for_templatetags/trip_list_table.html')
def trip_list_table(trip_list, approve_mode=False):
    return {'trip_list': trip_list, 'approve_mode': approve_mode}


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


@register.filter
def unapproved_trip_count(activity):
    today = date_utils.local_date()
    return models.Trip.objects.filter(
        trip_date__gte=today,
        activity=activity,
        chair_approved=False
    ).count()


@register.inclusion_tag('for_templatetags/trip_edit_buttons.html')
def trip_edit_buttons(trip, viewing_participant, viewing_user, hide_approve=False):
    return {'trip': trip,
            'chair_or_admin': perm_utils.chair_or_admin(viewing_user, trip.activity),
            'is_creator': trip.creator == viewing_participant,
            'hide_approve': hide_approve}
