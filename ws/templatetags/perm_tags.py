from django import template

from ws import models
import ws.utils.perms as perm_utils


register = template.Library()


@register.filter
def labeled_chair_activities(user):
    chair_activities = set(perm_utils.chair_activities(user, True))
    return [choice for choice in models.LeaderRating.CLOSED_ACTIVITY_CHOICES
            if choice[0] in chair_activities]
