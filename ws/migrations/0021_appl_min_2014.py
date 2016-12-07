# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import ws.utils.dates
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0020_leader_applications_2'),
    ]

    operations = [
        migrations.AlterField(
            model_name='winterschoolleaderapplication',
            name='year',
            field=models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)]),
        ),
    ]
