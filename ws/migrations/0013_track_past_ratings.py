# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import datetime
from django.utils.timezone import utc


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0012_trip_lottery_task_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='leaderrating',
            name='active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='leaderrating',
            name='creator',
            field=models.ForeignKey(related_name='ratings_created', default=1, to='ws.Participant'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='leaderrating',
            name='time_created',
            field=models.DateTimeField(default=datetime.datetime(2014, 1, 1, tzinfo=utc), auto_now_add=True),
            preserve_default=False,
        ),
    ]
