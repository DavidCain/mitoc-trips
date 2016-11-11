# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import ws.utils.dates
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0025_collect_complete_status'),
    ]

    operations = [
        migrations.RenameField(
            model_name='trip',
            old_name='wsc_approved',
            new_name='chair_approved',
        ),
        migrations.AlterField(
            model_name='winterschoolleaderapplication',
            name='year',
            field=models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)]),
        ),
    ]
