# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-09-18 02:01
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0008_distinctaccounts'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='leadersignup',
            unique_together=set([('participant', 'trip')]),
        ),
        migrations.AlterUniqueTogether(
            name='signup',
            unique_together=set([('participant', 'trip')]),
        ),
    ]
