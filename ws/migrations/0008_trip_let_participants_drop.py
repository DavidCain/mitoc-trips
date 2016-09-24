# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0007_snazzy_trips'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='let_participants_drop',
            field=models.BooleanField(default=False, help_text='Allow participants to remove themselves from the trip any time before its start date.'),
        ),
    ]
