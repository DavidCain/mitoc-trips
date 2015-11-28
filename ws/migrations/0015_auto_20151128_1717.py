# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0014_trip_activity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='car',
            name='year',
            field=models.PositiveIntegerField(validators=[django.core.validators.MaxValueValidator(2017), django.core.validators.MinValueValidator(1903)]),
        ),
        migrations.AlterField(
            model_name='emergencycontact',
            name='email',
            field=models.EmailField(max_length=254),
        ),
    ]
