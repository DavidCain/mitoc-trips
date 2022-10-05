from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0045_trip_search_vector_idx'),
    ]

    operations = [
        migrations.AddField(
            model_name='trip',
            name='summary',
            field=models.CharField(
                help_text="Brief summary of the trip, to be displayed on lists of all trips",
                max_length=80,
                null=True,
            ),
        ),
    ]
