import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F


def copy_user_id(apps, schema_editor):
    Participant = apps.get_model('ws', 'Participant')
    Participant.objects.update(temp_user_id=F('user_id'))


def do_nothing(*args):
    return


class Migration(migrations.Migration):
    """An lousy migration which is just working around Django's ORM.

    The whole point of this migration is to add a FK constraint to `user_id`.

    In raw SQL, it would be as simple as adding the constraint, since the
    column is already not nullable. However, I cannot find a way to get Django
    to recognize that `user_id` (an IntegerField) can become a ForeignKey.

    The approach below is not great. I could use raw SQL to get the job done,
    but Django's `makemigrations` will still think there are changes that
    need to be applied. This lets me avoid using `--fake` trickery.

    This just takes advantage of the fact that the participants table is
    quite small (~6,000), and we don't get a ton of new signups.
    """

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ws', '0035_bump_car_year_validator'),
    ]

    operations = [
        # Add a new column to represent the new FK constraint
        migrations.AddField(
            model_name='participant',
            name='temp_user',
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # Copy over all the FKs. We shouldn't get constraint violations here.
        migrations.RunPython(
            copy_user_id,
            reverse_code=do_nothing,
        ),
        # Remove the `not null` constraint, since the above RunPython handled it
        migrations.AlterField(
            model_name='participant',
            name='temp_user',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL
            ),
        ),
        # Remove the properly-named (but only a plain integer) `user_id` column.
        migrations.RemoveField(
            model_name='participant',
            name='user_id',
        ),
        # Finally, move the correct type of field back into position
        migrations.RenameField(
            model_name='participant',
            old_name='temp_user',
            new_name='user',
        ),
    ]
