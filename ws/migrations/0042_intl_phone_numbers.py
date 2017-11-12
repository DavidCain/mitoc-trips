# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations
import phonenumber_field.modelfields
from phonenumbers import format_number, is_valid_number, parse, PhoneNumberFormat


def new_number(us_num):
    """ Translate to E164, but toss out all the invalid numbers.

    Invalid numbers e.g. (000-000-0000) are often given out by international
    students who were frustrated that we requested only US numbers.

    Other numbers are given with bad area codes or similar, either because
    they assumed we'd parse a European number, or because they just made up
    a number.
    """
    if not is_valid_number(us_num):
        return ''
    return format_number(us_num, PhoneNumberFormat.E164)


def internationalize_phone_numbers(model_class):
    """ Take all instances of the model and internationalize the cell_phone.

    Translates `null` cell phone values to blank strings, since we're removing
    the `null=True` from Participant.cell_phone.

    Also strips invalid phone numbers so that we can re-collect them.
    """
    for model in model_class.objects.all():
        if not model.cell_phone:
            model.cell_phone = ''
        else:
            model.cell_phone = new_number(parse(model.cell_phone, 'US'))
        model.save()


def migrate_phone_numbers(apps, schema_editor):
    """ Convert US-formatted numbers to international ones. """
    internationalize_phone_numbers(apps.get_model("ws", "EmergencyContact"))
    internationalize_phone_numbers(apps.get_model("ws", "Participant"))


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0041_ws_application_corrections'),
    ]

    operations = [
        migrations.RunPython(migrate_phone_numbers),
        migrations.AlterField(
            model_name='emergencycontact',
            name='cell_phone',
            field=phonenumber_field.modelfields.PhoneNumberField(max_length=128),
        ),
        migrations.AlterField(
            model_name='participant',
            name='cell_phone',
            field=phonenumber_field.modelfields.PhoneNumberField(max_length=128, blank=True),
        ),
    ]
