# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0003_auto_20141103_1440'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='worry_time',
            field=models.CharField(default='Unknown', help_text='If the WIMP has not heard from you after this time and is unable to make contact with any leaders or participants, the authorities will be called.', max_length=63),
            preserve_default=False,
        ),
    ]
