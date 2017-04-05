# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0029_discount_report_access'),
    ]

    operations = [
        migrations.AddField(
            model_name='discount',
            name='administrators',
            field=models.ManyToManyField(help_text='Persons selected to administer this discount', to='ws.Participant', blank=True),
        ),
    ]
