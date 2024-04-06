from django import template
from django.contrib.auth.models import User

import ws.utils.perms as perm_utils
from ws import enums, models
from ws.utils.dates import local_date

register = template.Library()


@register.filter
def chair_activities(
    user: User | None,
    allow_superusers: bool = True,
) -> list[enums.Activity]:
    if user is None:
        return []
    return perm_utils.chair_activities(user, allow_superusers=allow_superusers)


@register.filter
def is_the_wimp(user: User, participant: models.Participant | None) -> bool:
    """Return True if the user has any upcoming WIMP trips."""
    if perm_utils.in_any_group(user, ["WIMP"], allow_superusers=True):
        return True
    if not participant:
        return False
    today = local_date()
    return participant.wimp_trips.filter(trip_date__gte=today).exists()
