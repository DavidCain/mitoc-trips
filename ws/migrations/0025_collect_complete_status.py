# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0024_winterschoolsettings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='participant',
            name='affiliation',
            field=models.CharField(max_length=2, choices=[('Undergraduate student', [('MU', 'MIT undergrad'), ('NU', 'Non-MIT undergrad')]), ('Graduate student', [('MG', 'MIT grad student'), ('NG', 'Non-MIT grad student')]), ('MA', 'MIT affiliate'), ('NA', 'Non-affiliate')]),
        ),
    ]
