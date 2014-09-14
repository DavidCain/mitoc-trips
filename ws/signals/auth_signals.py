from __future__ import unicode_literals

from django.contrib.auth.models import Group
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from ws.models import Leader


leaders_group = Group.objects.get(name='leaders')


@receiver(post_save, sender=Leader)
def add_leader_perms(sender, instance, created, raw, using, update_fields,
                     **kwargs):
    if created:
        leaders_group.user_set.add(instance.participant.user)
    print "Added {} to leaders group".format(instance)


@receiver(pre_delete, sender=Leader)
def remove_leader_perms(sender, instance, using, **kwargs):
    leaders_group.user_set.remove(instance.participant.user)
    print "Removed {} from leaders group".format(instance)
