# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0036_reword_allow_leader_signups'),
    ]

    operations = [
        migrations.AlterField(
            model_name='climbingleaderapplication',
            name='desired_rating',
            field=models.CharField(max_length=32, choices=[('Bouldering', 'Bouldering'), ('Single-pitch', 'Single-pitch'), ('Multi-pitch', 'Multi-pitch'), ('Bouldering + Single-pitch', 'Bouldering + Single-pitch'), ('Bouldering + Multi-pitch', 'Bouldering + Multi-pitch')]),
        ),
    ]
