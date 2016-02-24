# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import localflavor.us.models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0019_trip_level_20160118_2018'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leaderrating',
            name='activity',
            field=models.CharField(max_length='31', choices=[('biking', 'Biking'), ('boating', 'Boating'), ('cabin', 'Cabin'), ('climbing', 'Climbing'), ('hiking', 'Hiking'), ('winter_school', 'Winter School'), ('circus', 'Circus'), ('official_event', 'Official Event'), ('course', 'Course')]),
        ),
        migrations.AlterField(
            model_name='trip',
            name='activity',
            field=models.CharField(default='winter_school', max_length='31', choices=[('biking', 'Biking'), ('boating', 'Boating'), ('cabin', 'Cabin'), ('climbing', 'Climbing'), ('hiking', 'Hiking'), ('winter_school', 'Winter School'), ('circus', 'Circus'), ('official_event', 'Official Event'), ('course', 'Course')]),
        ),
    ]
