# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import datetime


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0007_auto_20150107_0033'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='leaderapplication',
            options={'ordering': ['id']},
        ),
        migrations.AddField(
            model_name='signup',
            name='last_updated',
            field=models.DateTimeField(default=datetime.datetime(2015, 1, 26, 9, 3, 15, 339398), auto_now=True),
            preserve_default=False,
        ),
        migrations.AlterModelOptions(
            name='signup',
            options={'ordering': ['last_updated']},
        ),
        migrations.AlterField(
            model_name='trip',
            name='notes',
            field=models.TextField(help_text='Participants must add notes to their signups if you complete this field. This is a great place to ask important questions.', max_length=2000, blank=True),
        ),
    ]
