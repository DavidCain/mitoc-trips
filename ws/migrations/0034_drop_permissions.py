"""
Delete all Permission objects, since I don't use the framework anyway.

The purpose of this migration is to remove the majority of foreign key
constraints in the `auth_db` database against the `django_content_type`
table. That table is replicated across both the `default` and the `auth_db`
databases, and rows have slightly different values in each.
"""

from django.db import migrations


def drop_perms(apps, schema_editor):
    """Delete all Permission objects.

    - These aren't in-use anyway
    - some refer to outdated dependencies (django-select2)
    - It's easy to re-create them later if we want them.

    Current permissions are basically (one per content type):
    - add
    - view
    - change
    - delete

    (In other words... CRUD)
    """
    # select count(*) from auth_user_user_permissions;  -- None in use!
    Permission = apps.get_model('auth', 'Permission')
    Permission.objects.all().delete()


def do_nothing(*args):
    return


class Migration(migrations.Migration):
    dependencies = [
        ('ws', '0033_discounts_optional_ga_key'),
    ]

    operations = [
        migrations.RunPython(
            drop_perms,
            reverse_code=do_nothing,
        )
    ]
