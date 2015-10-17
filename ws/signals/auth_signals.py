from __future__ import unicode_literals

from django.contrib.auth.models import Group
from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver

from ws.models import LeaderRating, Participant


leaders_group = Group.objects.get(name='leaders')
users_with_info = Group.objects.get(name='users_with_info')


@receiver(post_save, sender=LeaderRating)
def add_leader_perms(sender, instance, created, raw, using, update_fields,
                     **kwargs):
    if created:
        leaders_group.user_set.add(instance.participant.user)


@receiver(post_delete, sender=LeaderRating)
def remove_leader_perms(sender, instance, using, **kwargs):
    leader_ratings = instance.participant.leaderrating_set
    if not leader_ratings.exists():
        leaders_group.user_set.remove(instance.participant.user)


@receiver(post_save, sender=Participant)
def has_info(sender, instance, created, raw, using, update_fields, **kwargs):
    users_with_info.user_set.add(instance.user)


@receiver(pre_delete, sender=Participant)
def no_more_info(sender, instance, using, **kwargs):
    users_with_info.user_set.remove(instance.user)
