from ws import models


def chair_group(activity):
    if activity == 'winter_school':
        return 'WSC'
    return activity + '_chair'

def in_any_group(user, group_names, allow_superusers=True):
    if user.is_authenticated():
        if allow_superusers and user.is_superuser:
            return True
        return any(g.name in group_names for g in user.groups.all())


def is_chair(user, activity_type, allow_superusers=True):
    return in_any_group(user, [chair_group(activity_type)], allow_superusers)


activity_types = models.LeaderRating.ACTIVITIES
all_chair_groups = {chair_group(activity) for activity in activity_types}

def chair_activities(user, allow_superusers=False):
    """ All activities for which the user is the chair. """
    return [activity for activity in activity_types
            if is_chair(user, activity, allow_superusers)]

def chair_of_any_activity(user, allow_superusers=False):
    return bool(chair_activities(user, allow_superusers))
