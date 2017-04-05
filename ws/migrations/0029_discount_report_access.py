# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0028_configurable_discounts'),
    ]

    operations = [
        migrations.AddField(
            model_name='discount',
            name='report_access',
            field=models.BooleanField(default=False, help_text='Report if participant should have leader, student, or admin level access'),
        ),
    ]
