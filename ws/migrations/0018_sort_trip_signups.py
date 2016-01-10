# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import localflavor.us.models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0017_clarify_participant_email'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='signup',
            options={'ordering': ['manual_order', 'last_updated']},
        ),
        migrations.AddField(
            model_name='signup',
            name='manual_order',
            field=models.IntegerField(null=True, blank=True),
        ),
    ]
