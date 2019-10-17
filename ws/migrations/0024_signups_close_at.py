from django.db import migrations, models

import ws.utils.dates


class Migration(migrations.Migration):

    dependencies = [('ws', '0023_remove_trip_type_default')]

    operations = [
        migrations.AlterModelOptions(
            name='waitlistsignup',
            options={'ordering': ['-manual_order', 'time_created', 'pk']},
        ),
        migrations.AlterField(
            model_name='trip',
            name='signups_close_at',
            field=models.DateTimeField(
                blank=True, default=ws.utils.dates.default_signups_close_at, null=True
            ),
        ),
    ]
