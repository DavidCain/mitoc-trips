# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0042_intl_phone_numbers'),
    ]

    operations = [
        migrations.AlterField(
            model_name='car',
            name='year',
            field=models.PositiveIntegerField(validators=[django.core.validators.MaxValueValidator(2020), django.core.validators.MinValueValidator(1903)]),
        ),
    ]
