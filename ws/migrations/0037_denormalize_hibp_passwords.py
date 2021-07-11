# Generated by Django 2.2.24 on 2021-07-11 15:38

import django.db.models.deletion
from django.db import migrations, models


def copy_over_password_strength(apps, schema_editor):
    Participant = apps.get_model('ws', 'Participant')
    PasswordQuality = apps.get_model('ws', 'PasswordQuality')

    # Note that this isn't robust against new rows being created.
    # That's fine, though, since this isn't strictly necessary information
    PasswordQuality.objects.bulk_create(
        [
            PasswordQuality(
                participant=participant,
                is_insecure=participant.insecure_password,
                last_checked=participant.password_last_checked,
            )
            for participant in Participant.objects.all()
        ]
    )


def restore_participant_fields(apps, schema_editor):
    Participant = apps.get_model('ws', 'Participant')
    PasswordQuality = apps.get_model('ws', 'PasswordQuality')

    participants_to_update = []
    for pw in PasswordQuality.objects.all():
        pw.participant.insecure_password = pw.is_insecure
        pw.participant.password_last_checked = pw.last_checked
        participants_to_update.append(pw.participant)

    Participant.objects.bulk_update(
        participants_to_update, ['insecure_password', 'password_last_checked']
    )


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0036_par_user_id_fk'),
    ]

    operations = [
        migrations.CreateModel(
            name='PasswordQuality',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'is_insecure',
                    models.BooleanField(
                        default=False, verbose_name='Password shown to be insecure'
                    ),
                ),
                (
                    'last_checked',
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="Last time password was checked against HaveIBeenPwned's database",
                    ),
                ),
                (
                    'participant',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='ws.Participant',
                    ),
                ),
            ],
        ),
        migrations.RunPython(
            copy_over_password_strength, reverse_code=restore_participant_fields
        ),
        migrations.RemoveField(
            model_name='participant',
            name='insecure_password',
        ),
        migrations.RemoveField(
            model_name='participant',
            name='password_last_checked',
        ),
    ]
