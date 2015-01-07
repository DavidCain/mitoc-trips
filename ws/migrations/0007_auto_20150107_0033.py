# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0006_auto_20150106_1950'),
    ]

    operations = [
        migrations.AlterField(
            model_name='car',
            name='year',
            field=models.PositiveIntegerField(max_length=4, validators=[django.core.validators.MaxValueValidator(2017), django.core.validators.MinValueValidator(1903)]),
        ),
    ]
