# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0003_level_only_for_ws'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='allow_leader_signups',
            field=models.BooleanField(default=False, help_text='Allow leaders (with ratings for this activity) to sign themselves up for the trip any time before its date. Recommended for Circuses!'),
        ),
        migrations.CreateModel(
            name='LeaderSignUp',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('notes', models.TextField(max_length=1000, blank=True)),
                ('participant', models.ForeignKey(to='ws.Participant')),
                ('trip', models.ForeignKey(to='ws.Trip')),
            ],
            options={
                'ordering': ['time_created'],
            },
        ),
    ]
