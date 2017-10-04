# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def add_mentor_activities(apps, schema_editor):
    MentorActivity = apps.get_model('ws', 'MentorActivity')
    MentorActivity(name='Hiking').save()
    MentorActivity(name='Skiing').save()
    MentorActivity(name='Ice climbing').save()


def remove_mentor_activities(apps, schema_editor):
    MentorActivity = apps.get_model('ws', 'MentorActivity')
    MentorActivity.objects.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0039_discounts_administered'),
    ]

    operations = [
        migrations.CreateModel(
            name='MentorActivity',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(unique=True, max_length=31)),
            ],
        ),
        migrations.AddField(
            model_name='winterschoolleaderapplication',
            name='mentee_activities',
            field=models.ManyToManyField(related_name='mentee_activities', verbose_name='For which activities would you like a mentor?', to='ws.MentorActivity', blank=True, help_text="Please select at least one."),
        ),
        migrations.AddField(
            model_name='winterschoolleaderapplication',
            name='mentor_activities',
            field=models.ManyToManyField(related_name='activities_mentored', verbose_name='Which activities would you like to mentor?', to='ws.MentorActivity', blank=True, help_text="Please select at least one."),
        ),
        migrations.RunPython(add_mentor_activities, remove_mentor_activities)
    ]
