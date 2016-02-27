# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0020_new_activity_types'),
    ]

    operations = [
        migrations.RenameField(
            model_name='emergencycontact',
            old_name='contact_cell_phone',
            new_name='cell_phone',
        ),
        migrations.RenameField(
            model_name='emergencycontact',
            old_name='contact_email',
            new_name='email',
        ),
        migrations.RenameField(
            model_name='emergencycontact',
            old_name='contact_name',
            new_name='name',
        ),
        migrations.AlterField(
            model_name='car',
            name='year',
            field=models.PositiveIntegerField(validators=[django.core.validators.MaxValueValidator(2018), django.core.validators.MinValueValidator(1903)]),
        ),
    ]
