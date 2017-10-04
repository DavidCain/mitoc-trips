# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0040_winter_school_mentors'),
    ]

    operations = [
        migrations.AlterField(
            model_name='winterschoolleaderapplication',
            name='taking_wfa',
            field=models.CharField(help_text='Save $100 on the course fee by leading two or more trips!', max_length=10, verbose_name='Do you plan on taking the subsidized WFA at MIT?', choices=[('Yes', 'Yes'), ('No', 'No'), ('Maybe', "Maybe/don't know")]),
        ),
        migrations.AlterField(
            model_name='winterschoolleaderapplication',
            name='winter_experience',
            field=models.TextField(help_text='Details of previous winter outdoors experience. Include the type of trip (x-country skiiing, above treeline, snowshoeing, ice climbing, etc), approximate dates and locations, numbers of participants, notable trail and weather conditions. Please also give details of whether you participated, led, or co-led these trips.', max_length=5000, blank=True),
        ),
    ]
