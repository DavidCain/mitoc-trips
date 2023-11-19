# Signals are a terrible pattern that I aim to replace eventually.
# Ruff will complain about the large number of arguments. We can ignore for now.
# ruff: noqa: PLR0913
from django.contrib.auth.models import Group
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from ws.models import LeaderRating, Participant


def update_leader_status(participant):
    leader_ratings = participant.leaderrating_set.filter(active=True)
    if not leader_ratings.exists():
        Group.objects.get(name="leaders").user_set.remove(participant.user)


@receiver(post_save, sender=LeaderRating)
def modify_leader_perms(sender, instance, created, raw, using, update_fields, **kwargs):
    """When creating/updating leader permissions, update leader status.

    Participants belong to the 'leaders' group when they have an active
    leader rating. This signal exists so that modifications to LeaderRating
    objects
    """
    if created:
        leaders = Group.objects.get(name="leaders")
        leaders.user_set.add(instance.participant.user)
    else:  # Updating (maybe to inactive!)
        update_leader_status(instance.participant)


@receiver(post_delete, sender=LeaderRating)
def remove_leader_perms(sender, instance, using, **kwargs):
    """After a rating is removed, check if the participant is still a leader.

    In most cases, we'll probably just want to set the old rating as inactiive.
    However, this signal exists in case we wish to hard delete a rating.
    """
    update_leader_status(instance.participant)


@receiver(post_save, sender=Participant)
def has_info(sender, instance, created, raw, using, update_fields, **kwargs):
    Group.objects.get(name="users_with_info").user_set.add(instance.user)


@receiver(pre_delete, sender=Participant)
def no_more_info(sender, instance, using, **kwargs):
    Group.objects.get(name="users_with_info").user_set.remove(instance.user)
