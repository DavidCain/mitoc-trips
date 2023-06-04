# Generated by Django 3.2.16 on 2023-02-03 23:22

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('ws', '0053_index_key_trip_fields'),
    ]

    operations = [
        migrations.AlterField(
            model_name='membershipreminder',
            name='participant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.participant'
            ),
        ),
        migrations.AlterField(
            model_name='membershipreminder',
            name='reminder_sent_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Last time an email was sent reminding this participant to renew',
            ),
        ),
        migrations.AddConstraint(
            model_name='membershipreminder',
            constraint=models.UniqueConstraint(
                condition=models.Q(('reminder_sent_at__isnull', True)),
                fields=('participant',),
                name='ws_membershipreminder_par_reminder_sent_at_uniq',
            ),
        ),
    ]