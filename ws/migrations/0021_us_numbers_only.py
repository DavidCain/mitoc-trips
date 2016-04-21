# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import localflavor.us.models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0020_new_activity_types'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emergencycontact',
            name='contact_cell_phone',
            field=localflavor.us.models.PhoneNumberField(help_text='US numbers only, please', max_length=20, verbose_name='Cell phone'),
        ),
    ]
