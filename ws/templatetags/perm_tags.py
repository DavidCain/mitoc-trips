from django import template

register = template.Library()

from ws import perm_utils


@register.filter
def chair_of_any_activity(user):
    return perm_utils.chair_of_any_activity(user)
