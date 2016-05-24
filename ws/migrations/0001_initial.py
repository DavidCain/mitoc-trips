# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import ws.fields
import localflavor.us.models
import ws.utils.dates
from django.conf import settings
import django.utils.timezone
import ws.models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Car',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('license_plate', models.CharField(max_length=31, validators=[django.core.validators.RegexValidator('^[a-zA-Z0-9 ]*$', 'Only alphanumeric characters and spaces allowed')])),
                ('state', localflavor.us.models.USStateField(max_length=2, choices=[(b'AL', b'Alabama'), (b'AK', b'Alaska'), (b'AS', b'American Samoa'), (b'AZ', b'Arizona'), (b'AR', b'Arkansas'), (b'AA', b'Armed Forces Americas'), (b'AE', b'Armed Forces Europe'), (b'AP', b'Armed Forces Pacific'), (b'CA', b'California'), (b'CO', b'Colorado'), (b'CT', b'Connecticut'), (b'DE', b'Delaware'), (b'DC', b'District of Columbia'), (b'FL', b'Florida'), (b'GA', b'Georgia'), (b'GU', b'Guam'), (b'HI', b'Hawaii'), (b'ID', b'Idaho'), (b'IL', b'Illinois'), (b'IN', b'Indiana'), (b'IA', b'Iowa'), (b'KS', b'Kansas'), (b'KY', b'Kentucky'), (b'LA', b'Louisiana'), (b'ME', b'Maine'), (b'MD', b'Maryland'), (b'MA', b'Massachusetts'), (b'MI', b'Michigan'), (b'MN', b'Minnesota'), (b'MS', b'Mississippi'), (b'MO', b'Missouri'), (b'MT', b'Montana'), (b'NE', b'Nebraska'), (b'NV', b'Nevada'), (b'NH', b'New Hampshire'), (b'NJ', b'New Jersey'), (b'NM', b'New Mexico'), (b'NY', b'New York'), (b'NC', b'North Carolina'), (b'ND', b'North Dakota'), (b'MP', b'Northern Mariana Islands'), (b'OH', b'Ohio'), (b'OK', b'Oklahoma'), (b'OR', b'Oregon'), (b'PA', b'Pennsylvania'), (b'PR', b'Puerto Rico'), (b'RI', b'Rhode Island'), (b'SC', b'South Carolina'), (b'SD', b'South Dakota'), (b'TN', b'Tennessee'), (b'TX', b'Texas'), (b'UT', b'Utah'), (b'VT', b'Vermont'), (b'VI', b'Virgin Islands'), (b'VA', b'Virginia'), (b'WA', b'Washington'), (b'WV', b'West Virginia'), (b'WI', b'Wisconsin'), (b'WY', b'Wyoming')])),
                ('make', models.CharField(max_length=63)),
                ('model', models.CharField(max_length=63)),
                ('year', models.PositiveIntegerField(max_length=4, validators=[django.core.validators.MaxValueValidator(2016), django.core.validators.MinValueValidator(1903)])),
                ('color', models.CharField(max_length=63)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EmergencyContact',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('cell_phone', localflavor.us.models.PhoneNumberField(max_length=20)),
                ('relationship', models.CharField(max_length=63)),
                ('email', models.EmailField(max_length=75)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='EmergencyInfo',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('allergies', models.CharField(max_length=255)),
                ('medications', models.CharField(max_length=255)),
                ('medical_history', models.TextField(help_text='Anything your trip leader would want to know about.', max_length=2000)),
                ('emergency_contact', models.OneToOneField(to='ws.EmergencyContact')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Feedback',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('showed_up', models.BooleanField(default=True)),
                ('comments', models.TextField(max_length=2000)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['participant', 'time_created'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Leader',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('rating', models.CharField(max_length=31)),
                ('notes', models.TextField(max_length=500, blank=True)),
            ],
            options={
                'ordering': ['participant'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='LeaderApplication',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('previous_rating', models.CharField(help_text='Previous rating (if any)', max_length=255, blank=True)),
                ('desired_rating', models.CharField(max_length=255)),
                ('taking_wfa', models.CharField(help_text='Save $110 on the course fee by leading two or more trips!', max_length=10, verbose_name='Do you plan on taking the subsidized WFA at MIT?', choices=[('Yes', 'Yes'), ('No', 'No'), ('Maybe', "Maybe/don't know")])),
                ('training', models.TextField(help_text='Details of any medical, technical, or leadership training and qualifications relevant to the winter environment. State the approximate dates of these activities. Leave blank if not applicable.', max_length=5000, verbose_name='Formal training and qualifications', blank=True)),
                ('winter_experience', models.TextField(help_text='Details of previous winter outdoors experience. Include the type of trip (x-country skiiing, above treeline, snowshoeing, ice climbing, etc), approximate dates and locations, numbers of participants, notable trail and weather conditions. Please also give details of whether you participated, lead, or co-lead these trips.', max_length=5000, blank=True)),
                ('other_experience', models.TextField(help_text='Details about any relevant non-winter experience', max_length=5000, verbose_name='Other outdoors/leadership experience', blank=True)),
                ('notes_or_comments', models.TextField(help_text='Any relevant details, such as any limitations on availability on Tue/Thurs nights or weekends during IAP.', max_length=5000, blank=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='LotteryInfo',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('car_status', models.CharField(default='none', max_length=7, choices=[('none', 'No car'), ('own', 'Can drive own car'), ('rent', 'Willing to rent')])),
                ('number_of_passengers', models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MaxValueValidator(13, message='Do you drive a bus?')])),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['car_status', 'number_of_passengers'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Participant',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('cell_phone', localflavor.us.models.PhoneNumberField(max_length=20, null=True, blank=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('email', models.EmailField(unique=True, max_length=75)),
                ('affiliation', models.CharField(max_length=1, choices=[('S', 'MIT student'), ('M', 'MIT affiliate'), ('N', 'Non-affiliate')])),
                ('attended_lectures', models.BooleanField(default=False)),
                ('car', ws.fields.OptionalOneToOneField(null=True, blank=True, to='ws.Car')),
                ('emergency_info', models.OneToOneField(to='ws.EmergencyInfo')),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name', 'email'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='SignUp',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('notes', models.TextField(max_length=1000, blank=True)),
                ('order', models.IntegerField(null=True, blank=True)),
                ('on_trip', models.BooleanField(default=False)),
                ('participant', models.ForeignKey(to='ws.Participant')),
            ],
            options={
                'ordering': ['time_created'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='Trip',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=127)),
                ('description', models.TextField()),
                ('maximum_participants', models.PositiveIntegerField(default=8)),
                ('difficulty_rating', models.CharField(max_length=127)),
                ('prereqs', models.CharField(max_length=255, blank=True)),
                ('wsc_approved', models.BooleanField(default=False)),
                ('notes', models.TextField(max_length=2000, blank=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_edited', models.DateTimeField(auto_now=True)),
                ('trip_date', models.DateField(default=ws.utils.dates.nearest_sat)),
                ('signups_open_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('signups_close_at', models.DateTimeField(default=ws.utils.dates.closest_wed_at_noon, null=True, blank=True)),
                ('algorithm', models.CharField(default='lottery', max_length='31', choices=[('lottery', 'lottery'), ('fcfs', 'first-come, first-serve')])),
                ('creator', models.ForeignKey(related_name='created_trips', to='ws.Leader')),
                ('leaders', models.ManyToManyField(to='ws.Leader')),
                ('signed_up_participants', models.ManyToManyField(to='ws.Participant', through='ws.SignUp')),
            ],
            options={
                'ordering': ['-trip_date', '-time_created'],
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WaitList',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='WaitListSignup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('signup', models.OneToOneField(to='ws.SignUp')),
                ('waitlist', models.ForeignKey(to='ws.WaitList')),
            ],
            options={
                'ordering': ['time_created'],
            },
            bases=(models.Model,),
        ),
        migrations.AddField(
            model_name='waitlist',
            name='signups',
            field=models.ManyToManyField(to='ws.SignUp', through='ws.WaitListSignup'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='waitlist',
            name='trip',
            field=models.OneToOneField(to='ws.Trip'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='signup',
            name='trip',
            field=models.ForeignKey(to='ws.Trip'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='lotteryinfo',
            name='participant',
            field=models.OneToOneField(to='ws.Participant'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='leaderapplication',
            name='participant',
            field=models.OneToOneField(to='ws.Participant'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='leader',
            name='participant',
            field=models.OneToOneField(to='ws.Participant'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedback',
            name='leader',
            field=models.ForeignKey(to='ws.Leader'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedback',
            name='participant',
            field=models.ForeignKey(to='ws.Participant'),
            preserve_default=True,
        ),
        migrations.AddField(
            model_name='feedback',
            name='trip',
            field=models.ForeignKey(blank=True, to='ws.Trip', null=True),
            preserve_default=True,
        ),
    ]
