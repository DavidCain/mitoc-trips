from django.contrib.auth.models import Group, User
from ws import models


def is_leader(user):
    """ Return if the user is a trip leader.

    Take advantage of the prefetched 'leaders' group for more efficient
    querying of a user's leader status.
    """
    return in_any_group(user, ['leaders'], allow_superusers=False)


def chair_group(activity):
    if activity == 'winter_school':
        return 'WSC'
    return activity + '_chair'


def in_any_group(user, group_names, allow_superusers=True):
    if user.is_anonymous():
        return False

    if allow_superusers and user.is_superuser:
        search_groups = Group.objects.all()
    else:
        search_groups = user.groups.all()
    return any(g.name in group_names for g in search_groups)


def is_chair(user, activity_type, allow_superusers=True):
    return in_any_group(user, [chair_group(activity_type)], allow_superusers)


def num_chairs(activity):
    group = chair_group(activity)
    return User.objects.filter(groups__name=group).count()


activity_types = models.LeaderRating.ACTIVITIES
all_chair_groups = {chair_group(activity) for activity in activity_types}


def chair_activities(user, allow_superusers=False):
    """ All activities for which the user is the chair. """
    return [activity for activity in activity_types
            if is_chair(user, activity, allow_superusers)]
