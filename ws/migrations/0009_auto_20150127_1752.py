# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0008_auto_20150126_0903'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='difficulty_rating',
            field=models.CharField(max_length=63),
        ),
    ]
