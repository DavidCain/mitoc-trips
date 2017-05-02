# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0034_trip_lottery_log'),
    ]

    operations = [
        # First, create boolean field, applying temporary default of False
        # (Reflects that all past trips did not honor this setting)
        migrations.AddField(
            model_name='trip',
            name='honor_participant_pairing',
            field=models.BooleanField(default=False, help_text='Try to place paired participants together on the trip.'),
            preserve_default=False,
        ),
        # All trips from here on out default to True
        migrations.AlterField(
            model_name='trip',
            name='honor_participant_pairing',
            field=models.BooleanField(default=True, help_text='Try to place paired participants together on the trip.'),
        ),
    ]
