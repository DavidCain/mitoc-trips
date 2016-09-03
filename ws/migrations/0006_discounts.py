# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0005_markdown_helptext'),
    ]

    operations = [
        migrations.CreateModel(
            name='Discount',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('summary', models.CharField(max_length=255)),
                ('terms', models.TextField(max_length=4095)),
                ('url', models.URLField(null=True, blank=True)),
                ('ga_key', models.CharField(help_text='key for Google spreadsheet with membership information (shared as read-only with the company)', max_length=63)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name='participant',
            name='discounts',
            field=models.ManyToManyField(to='ws.Discount', blank=True),
        ),
    ]
