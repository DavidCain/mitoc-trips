# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0008_trip_let_participants_drop'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='maximum_participants',
            field=models.PositiveIntegerField(default=8, verbose_name='Max participants'),
        ),
        migrations.AlterField(
            model_name='trip',
            name='prereqs',
            field=models.CharField(max_length=255, verbose_name='Prerequisites', blank=True),
        ),
    ]
