# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0030_discount_administrators'),
    ]

    operations = [
        migrations.AddField(
            model_name='discount',
            name='report_student',
            field=models.BooleanField(default=False, help_text='Report MIT affiliation and student status to discount provider'),
        ),
        migrations.AddField(
            model_name='discount',
            name='report_school',
            field=models.BooleanField(default=False, help_text='Report MIT affiliation if participant is a student'),
        ),
    ]
