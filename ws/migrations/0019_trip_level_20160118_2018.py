# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import localflavor.us.models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0018_sort_trip_signups'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='level',
            field=models.CharField(default='Unknown', help_text="For Winter School, this trip's A, B, or C designation (plus I/S rating if applicable).", max_length=255),
            preserve_default=False,
        ),
    ]
