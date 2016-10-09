# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0010_change_email_help_link'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='leaders',
            field=models.ManyToManyField(related_name='trips_led', to='ws.Participant', blank=True),
        ),
    ]
