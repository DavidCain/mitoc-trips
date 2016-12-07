# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import ws.utils.dates
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0021_appl_min_2014'),
    ]

    operations = [
        migrations.CreateModel(
            name='HikingLeaderApplication',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('previous_rating', models.CharField(help_text='Previous rating (if any)', max_length=255, blank=True)),
                ('year', models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)])),
                ('desired_rating', models.CharField(help_text='Co-Leader: Can co-lead a 3-season hiking trip with a Leader. Leader: Can run 3-season hiking trips.', max_length=10, choices=[('Leader', 'Leader'), ('Co-Leader', 'Co-Leader')])),
                ('mitoc_experience', models.TextField(help_text='How long have you been a MITOC member? Please indicate what official MITOC hikes and Circuses you have been on. Include approximate dates and locations, number of participants, trail conditions, type of trip, etc. Give details of whether you participated, led, or co-led these trips. [Optional]: If you like, briefly summarize your experience on unofficial trips or experience outside of New England.', max_length=5000, verbose_name='Hiking Experience with MITOC')),
                ('formal_training', models.TextField(help_text='Please give details of any medical training and qualifications, with dates. Also include any other formal outdoor education or qualifications.', max_length=5000, blank=True)),
                ('leadership_experience', models.TextField(help_text="If you've been a leader elsewhere, please describe that here. This could include leadership in other collegiate outing clubs, student sports clubs, NOLS, Outward Bound, or AMC; working as a guide, summer camp counselor, or Scout leader; or organizing hikes with friends.", max_length=5000, verbose_name='Group outdoor/leadership experience', blank=True)),
                ('participant', models.ForeignKey(to='ws.Participant')),
            ],
            options={
                'ordering': ['time_created'],
                'abstract': False,
            },
        ),
    ]
