# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0001_squashed_0021_restore_econtact_names_20160227_1345'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tripinfo',
            name='drivers',
            field=models.ManyToManyField(help_text="If a trip participant is driving, but is not on this list, they must first submit <a href='/profile/edit/#car'>information about their car</a>. They should then be added here.", to='ws.Participant', blank=True),
        ),
    ]
