# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


trip_fixup = {}  # Stores the primary keys of participants for data migration


# Save participant IDs for reassignment (so we don't corrupt the leader fields)
# (There _must_ be a cleaner way to do data migrations on FKs, but it works)
def save_participant_ids(apps, schema_editor):
    Trip = apps.get_model("ws", "Trip")
    for trip in Trip.objects.all():
        leaders = [leader.participant.pk for leader in trip.leaders.all()]
        trip_fixup[trip.pk] = {"creator": trip.creator.participant.pk,
                               "leaders": leaders}


# After migrating the leader fields to point to participants, fix the PKs
def fix_leader_ids(apps, schema_editor):
    Trip = apps.get_model("ws", "Trip")
    Participant = apps.get_model("ws", "Participant")
    for trip in Trip.objects.all():
        trip.creator = Participant.objects.get(pk=trip_fixup[trip.pk]["creator"])
        trip.leaders = trip_fixup[trip.pk]["leaders"]
        trip.save()


def purge_feedback(apps, schema_editor):
    apps.get_model("ws", "Feedback").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0009_auto_20150127_1752'),
    ]

    operations = [
        # Switch trip leader fields over to use participants
        migrations.RunPython(save_participant_ids),
        migrations.AlterField(
            model_name='trip',
            name='leaders',
            field=models.ManyToManyField(related_name='trips_led', to=b'ws.Participant'),
        ),
        migrations.AlterField(
            model_name='trip',
            name='creator',
            field=models.ForeignKey(related_name='created_trips', to='ws.Participant'),
        ),
        migrations.RunPython(fix_leader_ids),

        # Switch feedback to be supplied by "participants," purge existing
        migrations.AlterField(
            model_name='feedback',
            name='leader',
            # Will point to the wrong participant, but we're going to purge anyway
            field=models.ForeignKey(related_name='authored_feedback', to='ws.Participant'),
        ),
        migrations.AlterModelOptions(
            name='feedback',
            options={'ordering': ['participant', '-time_created']},
        ),
        migrations.RunPython(purge_feedback),
    ]
