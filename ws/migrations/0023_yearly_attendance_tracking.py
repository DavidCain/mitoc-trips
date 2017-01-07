# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import ws.utils.dates
import django.core.validators


def store_2016_attendance(apps, schema_editor):
    """ The last record we have of lecture attendance is for 2016. """
    Participant = apps.get_model("ws", "Participant")
    if not Participant.objects.exists():
        return
    LectureAttendance = apps.get_model("ws", "LectureAttendance")
    admin = Participant.objects.get(pk=1)
    for par in Participant.objects.filter(attended_lectures=True):
        attended = LectureAttendance(year=2016, participant=par, creator=admin)
        attended.save()


def restore_attended_lectures(apps, schema_editor):
    Participant = apps.get_model("ws", "Participant")
    LectureAttendance = apps.get_model("ws", "LectureAttendance")
    for attended in LectureAttendance.objects.all():
        attended.participant.attended_lectures = True
        attended.participant.save()


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0022_hikingleaderapplication'),
    ]

    operations = [
        migrations.CreateModel(
            name='LectureAttendance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('year', models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Winter School year when lectures were attended.', validators=[django.core.validators.MinValueValidator(2016)])),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('participant', models.ForeignKey(to='ws.Participant')),
                ('creator', models.ForeignKey(to='ws.Participant', related_name='lecture_attendances_marked')),
            ],
        ),
        migrations.AlterField(
            model_name='car',
            name='year',
            field=models.PositiveIntegerField(validators=[django.core.validators.MaxValueValidator(2019), django.core.validators.MinValueValidator(1903)]),
        ),
        migrations.RunPython(store_2016_attendance, restore_attended_lectures),
        migrations.RemoveField(
            model_name='participant',
            name='attended_lectures',
        ),
    ]
