import functools
from collections.abc import Collection

from django.contrib.auth.models import AnonymousUser, Group, User
from django.db.models import QuerySet

from ws import enums, models


# This is technically only accurate when starting the web server,
# but that's okay (new groups are created extremely rarely)
# This allows us to avoid repeatedly querying groups.
@functools.cache
def all_group_names():
    return set(Group.objects.values_list("name", flat=True))


def is_leader(user: AnonymousUser | User) -> bool:
    """Return if the user is a trip leader.

    Take advantage of the prefetched 'leaders' group for more efficient
    querying of a user's leader status.
    """
    return in_any_group(user, ["leaders"], allow_superusers=False)


def leader_on_trip(
    participant: models.Participant,
    trip: models.Trip,
    creator_allowed: bool = False,
) -> bool:
    """Return if the participant is leading this trip.

    Optionally, the trip creator can be included even if they are not
    leading the trip.
    """
    if not participant:
        return False
    if participant in trip.leaders.all():
        return True
    return creator_allowed and participant == trip.creator


def chair_group(activity_enum: enums.Activity) -> str:
    if activity_enum == enums.Activity.WINTER_SCHOOL:
        return "WSC"
    return f"{activity_enum.value}_chair"


def in_any_group(
    user: AnonymousUser | User,
    group_names: Collection[str],
    allow_superusers: bool = True,
) -> bool:
    """Return if the user belongs to any of the passed groups.

    Group access control is used a lot in the app, so attempt to
    use groups already present on the `user` object, or a cached list of all
    group names. This will reduce needless queries.
    """
    if not user:  # TODO: I don't think this method ever has a null User called...
        return False
    if not user.is_authenticated:
        return False

    if allow_superusers and user.is_superuser:
        search_groups = all_group_names()
    else:
        # Do this in raw Python to avoid n+1 queries
        search_groups = {g.name for g in user.groups.all()}
    return any(g in group_names for g in search_groups)


def make_chair(user: User, activity_enum: enums.Activity) -> None:
    """Make the given user an activity chair!"""
    group_name = chair_group(activity_enum)
    group = Group.objects.get(name=group_name)
    user_set = group.user_set
    user_set.add(user)


def is_chair(
    user: AnonymousUser | User,
    activity_enum: enums.Activity | None,
    allow_superusers: bool = True,
) -> bool:
    """Return if the activity has chairs, and the user is one.

    If the user is an admin, return True if and only if that activity
    has chairs (e.g. even an admin can't be the chair of 'official events').
    """
    if activity_enum is None:  # (e.g. when the required activity is None)
        return False
    return in_any_group(user, [chair_group(activity_enum)], allow_superusers)


def chair_or_admin(
    user: AnonymousUser | User,
    activity_enum: enums.Activity,
) -> bool:
    """Return if the user is the chair of the activity, or if they're an admin.

    This is needed because some activity types (open activities) don't have
    any chairs by definition, but we still want to grant admins access as if
    they were activity chairs.
    """
    return user.is_superuser or is_chair(user, activity_enum, True)


def activity_chairs(activity_enum: enums.Activity) -> QuerySet[User]:
    return User.objects.filter(groups__name=chair_group(activity_enum))


def chair_activities(
    user: User,
    allow_superusers: bool = False,
) -> list[enums.Activity]:
    """All activities for which the user is the chair."""
    chair_group_to_activity: dict[str, enums.Activity] = {
        chair_group(activity_enum): activity_enum for activity_enum in enums.Activity
    }
    groups = Group.objects if allow_superusers and user.is_superuser else user.groups

    return sorted(
        (
            chair_group_to_activity[g.name]
            for g in groups.filter(name__in=chair_group_to_activity).order_by("name")
        ),
        key=lambda activity_enum: activity_enum.value,
    )
