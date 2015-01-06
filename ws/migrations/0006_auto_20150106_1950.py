# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import ws.fields
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0005_trip_worry_time'),
    ]

    operations = [
        migrations.CreateModel(
            name='TripInfo',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('start_location', models.CharField(max_length=127)),
                ('start_time', models.CharField(max_length=63)),
                ('turnaround_time', models.CharField(help_text="The time at which you'll turn back and head for your car/starting location", max_length=63, blank=True)),
                ('return_time', models.CharField(help_text='When you expect to return to your car/starting location and be able to call the WIMP', max_length=63)),
                ('worry_time', models.CharField(help_text='Suggested: return time +3 hours. If the WIMP has not heard from you after this time and is unable to make contact with any leaders or participants, the authorities will be called.', max_length=63)),
                ('itinerary', models.TextField(help_text='A detailed account of your trip plan. Where will you be going? What route will you be taking? Include trails, peaks, intermediate destinations, back-up plans- anything that would help rescuers find you.')),
                ('drivers', models.ManyToManyField(help_text="If a trip participant is driving, but is not on this list, they must first submit <a href='/update_info/#car'>information about their car</a>. They should then be added here.", to='ws.Participant', blank=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.RemoveField(
            model_name='trip',
            name='worry_time',
        ),
        migrations.AddField(
            model_name='trip',
            name='info',
            field=ws.fields.OptionalOneToOneField(null=True, blank=True, to='ws.TripInfo'),
            preserve_default=True,
        ),
    ]
