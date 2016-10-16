# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0011_allow_leaderless_trips'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='lottery_task_id',
            field=models.CharField(max_length='36', unique=True, null=True, blank=True),
        ),
    ]
