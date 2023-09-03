import re
from typing import TYPE_CHECKING

import markdown2
from bs4 import BeautifulSoup
from django.db import migrations, models

if TYPE_CHECKING:
    from ws.models import Trip


# (Essentially Trip.description_to_text as it existed at the time of this migration)
def description_to_text(trip: 'Trip') -> str:
    html = markdown2.markdown(trip.description)
    raw_text = BeautifulSoup(html, 'html.parser').text.strip()
    text = re.sub(r'[\s\n\r]+', ' ', raw_text)  # (make sure newlines are single spaces)
    if len(text) < 80:
        return text
    return text[:77].strip() + '...'


def save_trip_summary(apps, schema_editor):
    Trip = apps.get_model("ws", "Trip")
    for trip in Trip.objects.filter(summary__isnull=True):
        trip.summary = description_to_text(trip)
        assert len(trip.summary) <= 80, f"Summary too long: {trip.summary}"
        trip.save()


class Migration(migrations.Migration):
    dependencies = [
        ('ws', '0046_trip_summary'),
    ]

    operations = [
        migrations.RunPython(
            save_trip_summary,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='trip',
            name='summary',
            field=models.CharField(
                help_text="Brief summary of the trip, to be displayed on lists of all trips",
                max_length=80,
            ),
        ),
    ]
