from django import template

register = template.Library()

import ws.utils.perms


@register.filter
def chair_of_any_activity(user):
    return ws.utils.perms.chair_of_any_activity(user)
