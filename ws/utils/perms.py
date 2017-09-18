from django.contrib.auth.models import Group, User
from ws import models


# This is technically only accurate when starting the web server,
# but that's okay (new groups are created extremely rarely)
# This allows us to avoid repeatedly querying groups.
all_group_names = set(Group.objects.values_list('name', flat=True))


def is_leader(user):
    """ Return if the user is a trip leader.

    Take advantage of the prefetched 'leaders' group for more efficient
    querying of a user's leader status.
    """
    return in_any_group(user, ['leaders'], allow_superusers=False)


def leader_on_trip(participant, trip, creator_allowed=False):
    if not participant:
        return False
    return (participant in trip.leaders.all() or
            creator_allowed and participant == trip.creator)


def chair_group(activity):
    if activity in models.LeaderRating.OPEN_ACTIVITIES:
        raise ValueError("Open activities don't have chairs")

    if activity == 'winter_school':
        return 'WSC'
    return activity + '_chair'


def activity_name(activity):
    """ Human-readable activity name.

    'winter_school' -> 'Winter School'
    """
    return activity.replace('_', ' ').title()


def in_any_group(user, group_names, allow_superusers=True):
    if user.is_anonymous:
        return False

    if allow_superusers and user.is_superuser:
        search_groups = all_group_names
    else:
        search_groups = user.groups.values_list('name', flat=True)
    return any(g in group_names for g in search_groups)


def is_chair(user, activity_type, allow_superusers=True):
    """ Return if the activity has chairs, and the user is one.

    If the user is an admin, return True if and only if that activity
    has chairs (e.g. even an admin can't be the chair of 'official events').
    """
    if activity_type in models.LeaderRating.OPEN_ACTIVITIES:
        return False  # By definition, these don't have chairs
    return in_any_group(user, [chair_group(activity_type)], allow_superusers)


def chair_or_admin(user, activity_type):
    """ Return if the user is the chair of the activity, or if they're an admin.

    This is needed because some activity types (open activities) don't have
    any chairs by definition, but we still want to grant admins access as if
    they were activity chairs.
    """
    return True if user.is_superuser else is_chair(user, activity_type, True)


def num_chairs(activity):
    group = chair_group(activity)
    return User.objects.filter(groups__name=group).count()


activity_types = models.LeaderRating.CLOSED_ACTIVITIES
all_chair_groups = {chair_group(activity) for activity in activity_types}


def chair_activities(user, allow_superusers=False):
    """ All activities for which the user is the chair. """
    return [activity for activity in activity_types
            if is_chair(user, activity, allow_superusers)]
