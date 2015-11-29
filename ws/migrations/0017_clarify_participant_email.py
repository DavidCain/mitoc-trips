# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0016_rename_emergency_contact_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='participant',
            name='email',
            field=models.EmailField(help_text="This will be shared with leaders & other participants. <a href='/accounts/email/'>Change your account email</a>.", unique=True, max_length=254),
        ),
    ]
