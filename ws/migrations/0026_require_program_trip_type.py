"""
In the previous migration, we migrated over old activity information to form program.

We can now assign a `NOT NULL` constraint to the table.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ws', '0025_winterschoolsettings_accept_applications')]

    operations = [
        migrations.AlterField(
            model_name='trip',
            name='program',
            field=models.CharField(
                choices=[
                    (
                        'Specific rating required',
                        [
                            ('biking', 'Biking'),
                            ('boating', 'Boating'),
                            ('climbing', 'Climbing'),
                            ('hiking', '3-season hiking'),
                            ('mitoc_rock_program', 'MITOC Rock Program'),
                            ('winter_school', 'Winter School'),
                            ('winter_non_iap', 'Winter (outside IAP)'),
                        ],
                    ),
                    (
                        'Any leader rating allowed',
                        [
                            ('circus', 'Circus'),
                            ('service', 'Service'),
                            ('none', 'None'),
                        ],
                    ),
                ],
                max_length=255,
                # Namely, defaults to:
                # blank=False
                # null=False
            ),
        )
    ]
