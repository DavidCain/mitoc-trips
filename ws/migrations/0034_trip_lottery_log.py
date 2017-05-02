# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0033_rename_climbing_grades'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='lottery_log',
            field=models.TextField(null=True, blank=True),
        ),
    ]
