from django import template

from ws import models
import ws.utils.perms


register = template.Library()


@register.filter
def labeled_chair_activities(user):
    return [choice for choice in models.LeaderRating.CLOSED_ACTIVITY_CHOICES
            if choice[0] in ws.utils.perms.chair_activities(user)]
