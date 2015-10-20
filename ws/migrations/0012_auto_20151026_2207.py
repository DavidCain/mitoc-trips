# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0011_change_ratings_20151026_2150'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tripinfo',
            name='drivers',
            field=models.ManyToManyField(help_text="If a trip participant is driving, but is not on this list, they must first submit <a href='/personal_info/#car'>information about their car</a>. They should then be added here.", to=b'ws.Participant', blank=True),
        ),
    ]
