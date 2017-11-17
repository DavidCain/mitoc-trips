from django.contrib.auth.models import Group

from ws import models


def active_wimps():
    """ Yield all Participants that are currently WIMPs.

    Generally speaking, we should have only one WIMP, but we should handle the
    case of there being more than one, since the data model supports that.
    """
    users = Group.objects.get(name='WIMP').user_set
    recent_wimps = users.order_by('-auth_user_groups.id')  # Most recent first
    # NOTE: Coerced to a list so these queries can be executed across dbs
    wimp_users = list(recent_wimps.values_list('id', flat=True))
    par_by_user_id = {
        par.user_id: par
        for par in models.Participant.objects.filter(user_id__in=wimp_users)
    }
    for user_id in wimp_users:
        if user_id in par_by_user_id:
            yield par_by_user_id[user_id]


def current_wimp():
    try:
        return next(active_wimps())
    except StopIteration:
        return None
