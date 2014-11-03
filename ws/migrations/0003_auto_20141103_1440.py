# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0002_auto_20141031_1643'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='waitlistsignup',
            options={'ordering': ['-manual_order', 'time_created']},
        ),
        migrations.RenameField(
            model_name='waitlist',
            old_name='signups',
            new_name='unordered_signups',
        ),
        migrations.AddField(
            model_name='waitlistsignup',
            name='manual_order',
            field=models.IntegerField(null=True, blank=True),
            preserve_default=True,
        ),
    ]
