# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def nullify_non_ws_levels(apps, schema_editor):
    Trip = apps.get_model("ws", "Trip")
    for trip in Trip.objects.exclude(activity='winter_school'):
        trip.level = None
        trip.save()

def restore_levels(apps, schema_editor):
    Trip = apps.get_model("ws", "Trip")
    for trip in Trip.objects.all():
        trip.level = trip.level or "Unknown"
        trip.save()


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0002_update_info_path'),
    ]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='level',
            field=models.CharField(help_text="This trip's A, B, or C designation (plus I/S rating if applicable).", max_length=255, null=True, blank=True),
        ),
        migrations.RunPython(nullify_non_ws_levels, restore_levels),
    ]
