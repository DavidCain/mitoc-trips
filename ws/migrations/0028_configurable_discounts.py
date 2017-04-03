# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0027_not_driving'),
    ]

    operations = [
        migrations.AddField(
            model_name='discount',
            name='report_leader',
            field=models.BooleanField(default=False, help_text='Report MITOC leader status to discount provider'),
        ),
        migrations.AddField(
            model_name='discount',
            name='student_required',
            field=models.BooleanField(default=False, help_text='Discount provider requires recipients to be students'),
        ),
    ]
