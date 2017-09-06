# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0038_discount_active'),
    ]

    operations = [
        migrations.AlterField(
            model_name='discount',
            name='administrators',
            field=models.ManyToManyField(help_text='Persons selected to administer this discount', related_name='discounts_administered', to='ws.Participant', blank=True),
        ),
    ]
