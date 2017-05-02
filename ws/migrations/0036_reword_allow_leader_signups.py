# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0035_trip_honor_participant_pairing'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='allow_leader_signups',
            field=models.BooleanField(default=False, help_text='Allow leaders to sign themselves up as trip leaders. (Leaders can always sign up as participants). Recommended for Circuses!'),
        ),
    ]
