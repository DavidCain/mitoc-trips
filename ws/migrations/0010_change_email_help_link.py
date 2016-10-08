# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0009_change_trip_form_labels'),
    ]

    operations = [
        migrations.AlterField(
            model_name='participant',
            name='email',
            field=models.EmailField(help_text="This will be shared with leaders & other participants. <a href='/accounts/email/'>Manage email addresses</a>.", unique=True, max_length=254),
        ),
    ]
