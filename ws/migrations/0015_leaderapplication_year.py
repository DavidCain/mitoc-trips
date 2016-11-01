# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0014_estimate_rating_creation_times'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leaderapplication',
            name='participant',
            field=models.ForeignKey(to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='leaderapplication',
            name='year',
            field=models.PositiveIntegerField(default=2016, help_text='Winter School year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)]),
            preserve_default=False,
        ),
    ]
