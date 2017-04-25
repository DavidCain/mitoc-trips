# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import ws.utils.dates
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0031_discount_student_and_school'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClimbingLeaderApplication',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('previous_rating', models.CharField(help_text='Previous rating (if any)', max_length=255, blank=True)),
                ('year', models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)])),
                ('desired_rating', models.CharField(max_length=20, choices=[('Bouldering', 'Bouldering'), ('Single-pitch', 'Single-pitch'), ('Multi-pitch', 'Multi-pitch'), ('Bouldering + Single-pitch', 'Bouldering + Single-pitch'), ('Bouldering + Multi-pitch', 'Bouldering + Multi-pitch')])),
                ('years_climbing', models.IntegerField()),
                ('years_climbing_outside', models.IntegerField()),
                ('outdoor_bouldering_level', models.TextField(help_text='At what level are you comfortable bouldering outside?')),
                ('outdoor_sport_leading_level', models.TextField(help_text='At what level are you comfortable leading outside on sport routes?')),
                ('outdoor_trad_leading_level', models.TextField(help_text='At what level are you comfortable leading outside on trad routes?')),
                ('familiarity_spotting', models.CharField(max_length=16, verbose_name='Familarity with spotting boulder problems', choices=[('none', 'not at all'), ('some', 'some exposure'), ('comfortable', 'comfortable'), ('very comfortable', 'very comfortable')])),
                ('familiarity_bolt_anchors', models.CharField(max_length=16, verbose_name="Familiarity with 2-bolt 'sport' anchors", choices=[('none', 'not at all'), ('some', 'some exposure'), ('comfortable', 'comfortable'), ('very comfortable', 'very comfortable')])),
                ('familiarity_gear_anchors', models.CharField(max_length=16, verbose_name="Familiarity with trad 'gear' anchors", choices=[('none', 'not at all'), ('some', 'some exposure'), ('comfortable', 'comfortable'), ('very comfortable', 'very comfortable')])),
                ('familiarity_sr', models.CharField(max_length=16, verbose_name='Familiarity with multi-pitch self-rescue', choices=[('none', 'not at all'), ('some', 'some exposure'), ('comfortable', 'comfortable'), ('very comfortable', 'very comfortable')])),
                ('spotting_description', models.TextField(help_text='Describe how you would spot a climber on a meandering tall bouldering problem.', blank=True)),
                ('tr_anchor_description', models.TextField(help_text='Describe how you would build a top-rope anchor at a sport crag.', verbose_name='Top rope anchor description', blank=True)),
                ('rappel_description', models.TextField(help_text='Describe how you would set up a safe rappel.', blank=True)),
                ('gear_anchor_description', models.TextField(help_text='Describe what you look for when building a typical gear anchor.', blank=True)),
                ('formal_training', models.TextField(blank=True)),
                ('teaching_experience', models.TextField(blank=True)),
                ('notable_climbs', models.TextField(help_text='What are some particularly memorable climbs you have done?', blank=True)),
                ('favorite_route', models.TextField(help_text='Do you have a favorite route? If so, what is it and why?', blank=True)),
                ('extra_info', models.TextField(help_text='Is there anything else you would like us to know?', blank=True)),
                ('participant', models.ForeignKey(to='ws.Participant')),
            ],
            options={
                'ordering': ['time_created'],
                'abstract': False,
            },
        ),
    ]
