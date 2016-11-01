# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import datetime

from django.db import migrations
from django.utils import timezone


pytz_timezone = timezone.get_default_timezone()


def at_noon(day):
    noon = timezone.datetime(day.year, day.month, day.day, 12, 0, 0)
    return pytz_timezone.localize(noon)


def estimate_rating_creation(apps, schema_editor):
    """ Estimate the time that the rating was created.

    Since we didn't track this information initially, we can guess that ratings
    were created before the leader first led a trip.
    """

    LeaderRating = apps.get_model("ws", "LeaderRating")
    for rating in LeaderRating.objects.all():
        if rating.activity == 'winter_school':
            rating.time_created = at_noon(datetime(2016, 1, 1))
        else:
            leader = rating.participant
            trips = leader.trips_led.filter(activity=rating.activity)
            first = trips.order_by('time_created').first()

            date_created = first.trip_date if first else datetime(2016, 10, 31)
            rating.time_created = at_noon(date_created)

        rating.save()


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0013_track_past_ratings'),
    ]

    operations = [
        migrations.RunPython(estimate_rating_creation),
    ]
