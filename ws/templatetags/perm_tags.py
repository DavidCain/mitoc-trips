from django import template

from ws import models
from ws.utils.dates import local_date
import ws.utils.perms as perm_utils


register = template.Library()


@register.filter
def labeled_chair_activities(user):
    chair_activities = set(perm_utils.chair_activities(user, True))
    return [choice for choice in models.LeaderRating.CLOSED_ACTIVITY_CHOICES
            if choice[0] in chair_activities]


@register.filter
def is_the_wimp(user, participant):
    """ Return True if the user has any upcoming WIMP trips. """
    if perm_utils.in_any_group(user, ['WIMP'], allow_superusers=True):
        return True
    if not participant:
        return False
    today = local_date()
    return participant.wimp_trips.filter(trip_date__gte=today).exists()
