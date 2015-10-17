# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0010_remove_leaders_20151026_2106'),
    ]

    operations = [
        migrations.AddField(
            model_name='leader',
            name='activity',
            field=models.CharField(max_length='31', choices=[('hiking', 'Hiking'), ('climbing', 'Climbing'), ('winter_school', 'Winter School')]),
        ),
        migrations.AlterField(
            model_name='leader',
            name='participant',
            field=models.ForeignKey(to='ws.Participant'),
        ),
        migrations.RenameModel('Leader', 'LeaderRating'),
    ]
