# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0037_desired_rating_climbing'),
    ]

    operations = [
        migrations.AddField(
            model_name='discount',
            name='active',
            field=models.BooleanField(default=True, help_text='Discount is currently open & active'),
        ),
    ]
