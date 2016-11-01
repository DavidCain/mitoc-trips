# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import ws.utils.dates
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0015_leaderapplication_year'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leaderapplication',
            name='year',
            field=models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Winter School year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)]),
        ),
    ]
