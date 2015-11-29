# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0015_auto_20151128_1717'),
    ]

    operations = [
        migrations.RenameField(
            model_name='emergencycontact',
            old_name='cell_phone',
            new_name='contact_cell_phone',
        ),
        migrations.RenameField(
            model_name='emergencycontact',
            old_name='name',
            new_name='contact_name',
        ),
        migrations.RenameField(
            model_name='emergencycontact',
            old_name='email',
            new_name='contact_email',
        ),
    ]
