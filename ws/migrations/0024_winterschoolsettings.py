# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0023_yearly_attendance_tracking'),
    ]

    operations = [
        migrations.CreateModel(
            name='WinterSchoolSettings',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('allow_setting_attendance', models.BooleanField(default=False, verbose_name="Let participants set lecture attendance")),
                ('last_updated_by', models.ForeignKey(to='ws.Participant', null=True, blank=True)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
