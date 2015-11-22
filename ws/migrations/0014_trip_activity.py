# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0013_remove_leaders_20151026_2233'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='activity',
            field=models.CharField(default='winter_school', max_length='31', choices=[('hiking', 'Hiking'), ('climbing', 'Climbing'), ('winter_school', 'Winter School')]),
        ),
    ]
