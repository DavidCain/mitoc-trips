# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0016_auto_generate_years'),
    ]

    operations = [
        migrations.AddField(
            model_name='leaderapplication',
            name='activity',
            field=models.CharField(default='winter_school', max_length='31', choices=[('biking', 'Biking'), ('boating', 'Boating'), ('cabin', 'Cabin'), ('climbing', 'Climbing'), ('hiking', 'Hiking'), ('winter_school', 'Winter School'), ('circus', 'Circus'), ('official_event', 'Official Event'), ('course', 'Course')]),
        ),
    ]
