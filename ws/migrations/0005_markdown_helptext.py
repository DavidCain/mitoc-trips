# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0004_trip_allow_leader_signups'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='description',
            field=models.TextField(help_text='Markdown accepted here!'),
        ),
        migrations.AlterField(
            model_name='trip',
            name='notes',
            field=models.TextField(help_text='Participants must add notes to their signups if you complete this field. This is a great place to ask important questions. (Markdown accepted here!)', max_length=2000, blank=True),
        ),
    ]
