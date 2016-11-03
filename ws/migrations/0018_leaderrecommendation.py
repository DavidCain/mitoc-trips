# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0017_leaderapplication_activity'),
    ]

    operations = [
        migrations.CreateModel(
            name='LeaderRecommendation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('activity', models.CharField(max_length='31', choices=[('biking', 'Biking'), ('boating', 'Boating'), ('cabin', 'Cabin'), ('climbing', 'Climbing'), ('hiking', 'Hiking'), ('winter_school', 'Winter School'), ('circus', 'Circus'), ('official_event', 'Official Event'), ('course', 'Course')])),
                ('rating', models.CharField(max_length=31)),
                ('notes', models.TextField(max_length=500, blank=True)),
                ('creator', models.ForeignKey(related_name='recommendations_created', to='ws.Participant')),
                ('participant', models.ForeignKey(to='ws.Participant')),
            ],
            options={
                'ordering': ['participant'],
                'abstract': False,
            },
        ),
    ]
