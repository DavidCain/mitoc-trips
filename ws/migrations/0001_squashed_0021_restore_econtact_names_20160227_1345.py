# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import ws.fields
import localflavor.us.models
import ws.utils.dates
import django.utils.timezone
from django.conf import settings
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
                ('state', localflavor.us.models.USStateField(max_length=2, choices=[(b'AL', 'Alabama'), (b'AK', 'Alaska'), (b'AS', 'American Samoa'), (b'AZ', 'Arizona'), (b'AR', 'Arkansas'), (b'AA', 'Armed Forces Americas'), (b'AE', 'Armed Forces Europe'), (b'AP', 'Armed Forces Pacific'), (b'CA', 'California'), (b'CO', 'Colorado'), (b'CT', 'Connecticut'), (b'DE', 'Delaware'), (b'DC', 'District of Columbia'), (b'FL', 'Florida'), (b'GA', 'Georgia'), (b'GU', 'Guam'), (b'HI', 'Hawaii'), (b'ID', 'Idaho'), (b'IL', 'Illinois'), (b'IN', 'Indiana'), (b'IA', 'Iowa'), (b'KS', 'Kansas'), (b'KY', 'Kentucky'), (b'LA', 'Louisiana'), (b'ME', 'Maine'), (b'MD', 'Maryland'), (b'MA', 'Massachusetts'), (b'MI', 'Michigan'), (b'MN', 'Minnesota'), (b'MS', 'Mississippi'), (b'MO', 'Missouri'), (b'MT', 'Montana'), (b'NE', 'Nebraska'), (b'NV', 'Nevada'), (b'NH', 'New Hampshire'), (b'NJ', 'New Jersey'), (b'NM', 'New Mexico'), (b'NY', 'New York'), (b'NC', 'North Carolina'), (b'ND', 'North Dakota'), (b'MP', 'Northern Mariana Islands'), (b'OH', 'Ohio'), (b'OK', 'Oklahoma'), (b'OR', 'Oregon'), (b'PA', 'Pennsylvania'), (b'PR', 'Puerto Rico'), (b'RI', 'Rhode Island'), (b'SC', 'South Carolina'), (b'SD', 'South Dakota'), (b'TN', 'Tennessee'), (b'TX', 'Texas'), (b'UT', 'Utah'), (b'VT', 'Vermont'), (b'VI', 'Virgin Islands'), (b'VA', 'Virginia'), (b'WA', 'Washington'), (b'WV', 'West Virginia'), (b'WI', 'Wisconsin'), (b'WY', 'Wyoming')])),
                ('make', models.CharField(max_length=63)),
                ('model', models.CharField(max_length=63)),
                ('year', models.PositiveIntegerField(validators=[django.core.validators.MaxValueValidator(2018), django.core.validators.MinValueValidator(1903)])),
                ('color', models.CharField(max_length=63)),
            ],
        ),
        migrations.CreateModel(
            name='EmergencyContact',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('cell_phone', localflavor.us.models.PhoneNumberField(max_length=20)),
                ('relationship', models.CharField(max_length=63)),
                ('email', models.EmailField(max_length=254)),
            ],
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
                'ordering': ['participant', '-time_created'],
            },
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
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='LeaderRating',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('activity', models.CharField(max_length='31', choices=[('biking', 'Biking'), ('boating', 'Boating'), ('cabin', 'Cabin'), ('climbing', 'Climbing'), ('hiking', 'Hiking'), ('winter_school', 'Winter School'), ('circus', 'Circus'), ('official_event', 'Official Event'), ('course', 'Course')])),
                ('rating', models.CharField(max_length=31)),
                ('notes', models.TextField(max_length=500, blank=True)),
            ],
            options={
                'ordering': ['participant'],
            },
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
        ),
        migrations.CreateModel(
            name='Participant',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=255)),
                ('cell_phone', localflavor.us.models.PhoneNumberField(max_length=20, null=True, blank=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('email', models.EmailField(help_text="This will be shared with leaders & other participants. <a href='/accounts/email/'>Change your account email</a>.", unique=True, max_length=254)),
                ('affiliation', models.CharField(max_length=1, choices=[('S', 'MIT student'), ('M', 'MIT affiliate'), ('N', 'Non-affiliate')])),
                ('attended_lectures', models.BooleanField(default=False)),
                ('car', ws.fields.OptionalOneToOneField(null=True, blank=True, to='ws.Car')),
                ('emergency_info', models.OneToOneField(to='ws.EmergencyInfo')),
                ('user_id', models.IntegerField()),
            ],
            options={
                'ordering': ['name', 'email'],
            },
        ),
        migrations.CreateModel(
            name='SignUp',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('notes', models.TextField(max_length=1000, blank=True)),
                ('order', models.IntegerField(null=True, blank=True)),
                ('manual_order', models.IntegerField(null=True, blank=True)),
                ('on_trip', models.BooleanField(default=False)),
                ('participant', models.ForeignKey(to='ws.Participant')),
            ],
            options={
                'ordering': ['manual_order', 'last_updated'],
            },
        ),
        migrations.CreateModel(
            name='Trip',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('activity', models.CharField(default='winter_school', max_length='31', choices=[('biking', 'Biking'), ('boating', 'Boating'), ('cabin', 'Cabin'), ('climbing', 'Climbing'), ('hiking', 'Hiking'), ('winter_school', 'Winter School'), ('circus', 'Circus'), ('official_event', 'Official Event'), ('course', 'Course')])),
                ('name', models.CharField(max_length=127)),
                ('description', models.TextField()),
                ('maximum_participants', models.PositiveIntegerField(default=8)),
                ('difficulty_rating', models.CharField(max_length=63)),
                ('level', models.CharField(help_text="For Winter School, this trip's A, B, or C designation (plus I/S rating if applicable).", max_length=255)),
                ('prereqs', models.CharField(max_length=255, blank=True)),
                ('wsc_approved', models.BooleanField(default=False)),
                ('notes', models.TextField(help_text='Participants must add notes to their signups if you complete this field. This is a great place to ask important questions.', max_length=2000, blank=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_edited', models.DateTimeField(auto_now=True)),
                ('trip_date', models.DateField(default=ws.utils.dates.nearest_sat)),
                ('signups_open_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('signups_close_at', models.DateTimeField(default=ws.utils.dates.wed_morning, null=True, blank=True)),
                ('algorithm', models.CharField(default='lottery', max_length='31', choices=[('lottery', 'lottery'), ('fcfs', 'first-come, first-serve')])),
                ('creator', models.ForeignKey(related_name='created_trips', to='ws.Participant')),
            ],
            options={
                'ordering': ['-trip_date', '-time_created'],
            },
        ),
        migrations.CreateModel(
            name='TripInfo',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('start_location', models.CharField(max_length=127)),
                ('start_time', models.CharField(max_length=63)),
                ('turnaround_time', models.CharField(help_text="The time at which you'll turn back and head for your car/starting location", max_length=63, blank=True)),
                ('return_time', models.CharField(help_text='When you expect to return to your car/starting location and be able to call the WIMP', max_length=63)),
                ('worry_time', models.CharField(help_text='Suggested: return time +3 hours. If the WIMP has not heard from you after this time and is unable to make contact with any leaders or participants, the authorities will be called.', max_length=63)),
                ('itinerary', models.TextField(help_text='A detailed account of your trip plan. Where will you be going? What route will you be taking? Include trails, peaks, intermediate destinations, back-up plans- anything that would help rescuers find you.')),
                ('drivers', models.ManyToManyField(help_text="If a trip participant is driving, but is not on this list, they must first submit <a href='/personal_info/#car'>information about their car</a>. They should then be added here.", to='ws.Participant', blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='WaitList',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('trip', models.OneToOneField(to='ws.Trip')),
            ],
        ),
        migrations.CreateModel(
            name='WaitListSignup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('manual_order', models.IntegerField(null=True, blank=True)),
                ('signup', models.OneToOneField(to='ws.SignUp')),
                ('waitlist', models.ForeignKey(to='ws.WaitList')),
            ],
            options={
                'ordering': ['-manual_order', 'time_created'],
            },
        ),
        migrations.AddField(
            model_name='waitlist',
            name='unordered_signups',
            field=models.ManyToManyField(to='ws.SignUp', through='ws.WaitListSignup'),
        ),
        migrations.AddField(
            model_name='trip',
            name='info',
            field=ws.fields.OptionalOneToOneField(null=True, blank=True, to='ws.TripInfo'),
        ),
        migrations.AddField(
            model_name='trip',
            name='leaders',
            field=models.ManyToManyField(related_name='trips_led', to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='trip',
            name='signed_up_participants',
            field=models.ManyToManyField(to='ws.Participant', through='ws.SignUp'),
        ),
        migrations.AddField(
            model_name='signup',
            name='trip',
            field=models.ForeignKey(to='ws.Trip'),
        ),
        migrations.AddField(
            model_name='lotteryinfo',
            name='paired_with',
            field=models.ForeignKey(related_name='paired_by', blank=True, to='ws.Participant', null=True),
        ),
        migrations.AddField(
            model_name='lotteryinfo',
            name='participant',
            field=models.OneToOneField(to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='leaderrating',
            name='participant',
            field=models.ForeignKey(to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='leaderapplication',
            name='participant',
            field=models.OneToOneField(to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='feedback',
            name='leader',
            field=models.ForeignKey(related_name='authored_feedback', to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='feedback',
            name='participant',
            field=models.ForeignKey(to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='feedback',
            name='trip',
            field=models.ForeignKey(blank=True, to='ws.Trip', null=True),
        ),
    ]
