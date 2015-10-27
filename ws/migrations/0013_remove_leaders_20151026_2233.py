# -*- coding: utf-8 -*-
from django.contrib.auth.models import Group
from django.db import migrations


def remove_leaders(apps, schema_editor):
    LeaderRating = apps.get_model("ws", "LeaderRating")
    leader_group = Group.objects.get(name='leaders')
    LeaderRating.objects.all().delete()
    leader_group.user_set.clear()  # (Normally done automatically by signals)


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0012_auto_20151026_2207'),
    ]

    operations = [
        migrations.RunPython(remove_leaders),
    ]
