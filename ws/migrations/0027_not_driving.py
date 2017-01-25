# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0026_rename_chair_approval'),
    ]

    operations = [
        migrations.AlterField(
            model_name='lotteryinfo',
            name='car_status',
            field=models.CharField(default='none', max_length=7, choices=[('none', 'Not driving'), ('own', 'Can drive own car'), ('rent', 'Willing to rent')]),
        ),
    ]
