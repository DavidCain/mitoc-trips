# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0019_leader_applications'),
    ]

    operations = [
        migrations.RenameModel('LeaderApplication', 'WinterSchoolLeaderApplication'),
        migrations.AlterModelOptions(
            name='winterschoolleaderapplication',
            options={'ordering': ['time_created']},
        ),
        migrations.RemoveField(
            model_name='winterschoolleaderapplication',
            name='activity',
        ),
    ]
