# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import ws.utils.dates


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='lotteryinfo',
            name='paired_with',
            field=models.ForeignKey(related_name='paired_by', blank=True, to='ws.Participant', null=True),
            preserve_default=True,
        ),
        migrations.AlterField(
            model_name='trip',
            name='signups_close_at',
            field=models.DateTimeField(default=ws.utils.dates.wed_morning, null=True, blank=True),
        ),
    ]
