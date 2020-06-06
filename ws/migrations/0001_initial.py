# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from typing import List, Tuple

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import localflavor.us.models
import phonenumber_field.modelfields
from django.db import migrations, models

import ws.fields
import ws.utils.dates


class Migration(migrations.Migration):

    initial = True

    dependencies: List[Tuple[str, str]] = []

    operations = [
        migrations.CreateModel(
            name='Car',
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
                    'license_plate',
                    models.CharField(
                        max_length=31,
                        validators=[
                            django.core.validators.RegexValidator(
                                '^[a-zA-Z0-9 ]*$',
                                'Only alphanumeric characters and spaces allowed',
                            )
                        ],
                    ),
                ),
                ('state', localflavor.us.models.USStateField(max_length=2)),
                ('make', models.CharField(max_length=63)),
                ('model', models.CharField(max_length=63)),
                (
                    'year',
                    models.PositiveIntegerField(
                        validators=[
                            django.core.validators.MaxValueValidator(2020),
                            django.core.validators.MinValueValidator(1903),
                        ]
                    ),
                ),
                ('color', models.CharField(max_length=63)),
            ],
        ),
        migrations.CreateModel(
            name='ClimbingLeaderApplication',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                (
                    'previous_rating',
                    models.CharField(
                        blank=True, help_text='Previous rating (if any)', max_length=255
                    ),
                ),
                (
                    'year',
                    models.PositiveIntegerField(
                        default=ws.utils.dates.ws_year,
                        help_text='Year this application pertains to.',
                        validators=[django.core.validators.MinValueValidator(2014)],
                    ),
                ),
                (
                    'desired_rating',
                    models.CharField(
                        choices=[
                            ('Bouldering', 'Bouldering'),
                            ('Single-pitch', 'Single-pitch'),
                            ('Multi-pitch', 'Multi-pitch'),
                            ('Bouldering + Single-pitch', 'Bouldering + Single-pitch'),
                            ('Bouldering + Multi-pitch', 'Bouldering + Multi-pitch'),
                        ],
                        max_length=32,
                    ),
                ),
                ('years_climbing', models.IntegerField()),
                ('years_climbing_outside', models.IntegerField()),
                (
                    'outdoor_bouldering_grade',
                    models.CharField(
                        help_text='At what grade are you comfortable bouldering outside?',
                        max_length=255,
                    ),
                ),
                (
                    'outdoor_sport_leading_grade',
                    models.CharField(
                        help_text='At what grade are you comfortable leading outside on sport routes?',
                        max_length=255,
                    ),
                ),
                (
                    'outdoor_trad_leading_grade',
                    models.CharField(
                        help_text='At what grade are you comfortable leading outside on trad routes?',
                        max_length=255,
                    ),
                ),
                (
                    'familiarity_spotting',
                    models.CharField(
                        choices=[
                            ('none', 'not at all'),
                            ('some', 'some exposure'),
                            ('comfortable', 'comfortable'),
                            ('very comfortable', 'very comfortable'),
                        ],
                        max_length=16,
                        verbose_name='Familarity with spotting boulder problems',
                    ),
                ),
                (
                    'familiarity_bolt_anchors',
                    models.CharField(
                        choices=[
                            ('none', 'not at all'),
                            ('some', 'some exposure'),
                            ('comfortable', 'comfortable'),
                            ('very comfortable', 'very comfortable'),
                        ],
                        max_length=16,
                        verbose_name="Familiarity with 2-bolt 'sport' anchors",
                    ),
                ),
                (
                    'familiarity_gear_anchors',
                    models.CharField(
                        choices=[
                            ('none', 'not at all'),
                            ('some', 'some exposure'),
                            ('comfortable', 'comfortable'),
                            ('very comfortable', 'very comfortable'),
                        ],
                        max_length=16,
                        verbose_name="Familiarity with trad 'gear' anchors",
                    ),
                ),
                (
                    'familiarity_sr',
                    models.CharField(
                        choices=[
                            ('none', 'not at all'),
                            ('some', 'some exposure'),
                            ('comfortable', 'comfortable'),
                            ('very comfortable', 'very comfortable'),
                        ],
                        max_length=16,
                        verbose_name='Familiarity with multi-pitch self-rescue',
                    ),
                ),
                (
                    'spotting_description',
                    models.TextField(
                        blank=True,
                        help_text='Describe how you would spot a climber on a meandering tall bouldering problem.',
                    ),
                ),
                (
                    'tr_anchor_description',
                    models.TextField(
                        blank=True,
                        help_text='Describe how you would build a top-rope anchor at a sport crag.',
                        verbose_name='Top rope anchor description',
                    ),
                ),
                (
                    'rappel_description',
                    models.TextField(
                        blank=True,
                        help_text='Describe how you would set up a safe rappel.',
                    ),
                ),
                (
                    'gear_anchor_description',
                    models.TextField(
                        blank=True,
                        help_text='Describe what you look for when building a typical gear anchor.',
                    ),
                ),
                ('formal_training', models.TextField(blank=True)),
                ('teaching_experience', models.TextField(blank=True)),
                (
                    'notable_climbs',
                    models.TextField(
                        blank=True,
                        help_text='What are some particularly memorable climbs you have done?',
                    ),
                ),
                (
                    'favorite_route',
                    models.TextField(
                        blank=True,
                        help_text='Do you have a favorite route? If so, what is it and why?',
                    ),
                ),
                (
                    'extra_info',
                    models.TextField(
                        blank=True,
                        help_text='Is there anything else you would like us to know?',
                    ),
                ),
            ],
            options={'ordering': ['time_created'], 'abstract': False},
        ),
        migrations.CreateModel(
            name='Discount',
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
                    'active',
                    models.BooleanField(
                        default=True, help_text='Discount is currently open & active'
                    ),
                ),
                ('name', models.CharField(max_length=255)),
                ('summary', models.CharField(max_length=255)),
                ('terms', models.TextField(max_length=4095)),
                ('url', models.URLField(blank=True, null=True)),
                (
                    'ga_key',
                    models.CharField(
                        help_text='key for Google spreadsheet with membership information (shared as read-only with the company)',
                        max_length=63,
                    ),
                ),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                (
                    'student_required',
                    models.BooleanField(
                        default=False,
                        help_text='Discount provider requires recipients to be students',
                    ),
                ),
                (
                    'report_school',
                    models.BooleanField(
                        default=False,
                        help_text='Report MIT affiliation if participant is a student',
                    ),
                ),
                (
                    'report_student',
                    models.BooleanField(
                        default=False,
                        help_text='Report MIT affiliation and student status to discount provider',
                    ),
                ),
                (
                    'report_leader',
                    models.BooleanField(
                        default=False,
                        help_text='Report MITOC leader status to discount provider',
                    ),
                ),
                (
                    'report_access',
                    models.BooleanField(
                        default=False,
                        help_text='Report if participant should have leader, student, or admin level access',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='EmergencyContact',
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
                ('name', models.CharField(max_length=255)),
                (
                    'cell_phone',
                    phonenumber_field.modelfields.PhoneNumberField(max_length=128),
                ),
                ('relationship', models.CharField(max_length=63)),
                ('email', models.EmailField(max_length=254)),
            ],
        ),
        migrations.CreateModel(
            name='EmergencyInfo',
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
                ('allergies', models.CharField(max_length=255)),
                ('medications', models.CharField(max_length=255)),
                (
                    'medical_history',
                    models.TextField(
                        help_text='Anything your trip leader would want to know about.',
                        max_length=2000,
                    ),
                ),
                (
                    'emergency_contact',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='ws.EmergencyContact',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='Feedback',
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
                ('showed_up', models.BooleanField(default=True)),
                ('comments', models.TextField(max_length=2000)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
            ],
            options={'ordering': ['participant', '-time_created']},
        ),
        migrations.CreateModel(
            name='HikingLeaderApplication',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                (
                    'previous_rating',
                    models.CharField(
                        blank=True, help_text='Previous rating (if any)', max_length=255
                    ),
                ),
                (
                    'year',
                    models.PositiveIntegerField(
                        default=ws.utils.dates.ws_year,
                        help_text='Year this application pertains to.',
                        validators=[django.core.validators.MinValueValidator(2014)],
                    ),
                ),
                (
                    'desired_rating',
                    models.CharField(
                        choices=[('Leader', 'Leader'), ('Co-Leader', 'Co-Leader')],
                        help_text='Co-Leader: Can co-lead a 3-season hiking trip with a Leader. Leader: Can run 3-season hiking trips.',
                        max_length=10,
                    ),
                ),
                (
                    'mitoc_experience',
                    models.TextField(
                        help_text='How long have you been a MITOC member? Please indicate what official MITOC hikes and Circuses you have been on. Include approximate dates and locations, number of participants, trail conditions, type of trip, etc. Give details of whether you participated, led, or co-led these trips. [Optional]: If you like, briefly summarize your experience on unofficial trips or experience outside of New England.',
                        max_length=5000,
                        verbose_name='Hiking Experience with MITOC',
                    ),
                ),
                (
                    'formal_training',
                    models.TextField(
                        blank=True,
                        help_text='Please give details of any medical training and qualifications, with dates. Also include any other formal outdoor education or qualifications.',
                        max_length=5000,
                    ),
                ),
                (
                    'leadership_experience',
                    models.TextField(
                        blank=True,
                        help_text="If you've been a leader elsewhere, please describe that here. This could include leadership in other collegiate outing clubs, student sports clubs, NOLS, Outward Bound, or AMC; working as a guide, summer camp counselor, or Scout leader; or organizing hikes with friends.",
                        max_length=5000,
                        verbose_name='Group outdoor/leadership experience',
                    ),
                ),
            ],
            options={'ordering': ['time_created'], 'abstract': False},
        ),
        migrations.CreateModel(
            name='LeaderRating',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                (
                    'activity',
                    models.CharField(
                        choices=[
                            ('biking', 'Biking'),
                            ('boating', 'Boating'),
                            ('cabin', 'Cabin'),
                            ('climbing', 'Climbing'),
                            ('hiking', 'Hiking'),
                            ('winter_school', 'Winter School'),
                            ('circus', 'Circus'),
                            ('official_event', 'Official Event'),
                            ('course', 'Course'),
                        ],
                        max_length=31,
                    ),
                ),
                ('rating', models.CharField(max_length=31)),
                ('notes', models.TextField(blank=True, max_length=500)),
                ('active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['participant'], 'abstract': False},
        ),
        migrations.CreateModel(
            name='LeaderRecommendation',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                (
                    'activity',
                    models.CharField(
                        choices=[
                            ('biking', 'Biking'),
                            ('boating', 'Boating'),
                            ('cabin', 'Cabin'),
                            ('climbing', 'Climbing'),
                            ('hiking', 'Hiking'),
                            ('winter_school', 'Winter School'),
                            ('circus', 'Circus'),
                            ('official_event', 'Official Event'),
                            ('course', 'Course'),
                        ],
                        max_length=31,
                    ),
                ),
                ('rating', models.CharField(max_length=31)),
                ('notes', models.TextField(blank=True, max_length=500)),
            ],
            options={'ordering': ['participant'], 'abstract': False},
        ),
        migrations.CreateModel(
            name='LeaderSignUp',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('notes', models.TextField(blank=True, max_length=1000)),
            ],
            options={'ordering': ['time_created']},
        ),
        migrations.CreateModel(
            name='LectureAttendance',
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
                    'year',
                    models.PositiveIntegerField(
                        default=ws.utils.dates.ws_year,
                        help_text='Winter School year when lectures were attended.',
                        validators=[django.core.validators.MinValueValidator(2016)],
                    ),
                ),
                ('time_created', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='LotteryInfo',
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
                    'car_status',
                    models.CharField(
                        choices=[
                            ('none', 'Not driving'),
                            ('own', 'Can drive own car'),
                            ('rent', 'Willing to rent'),
                        ],
                        default='none',
                        max_length=7,
                    ),
                ),
                (
                    'number_of_passengers',
                    models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        validators=[
                            django.core.validators.MaxValueValidator(
                                13, message='Do you drive a bus?'
                            )
                        ],
                    ),
                ),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
            options={'ordering': ['car_status', 'number_of_passengers']},
        ),
        migrations.CreateModel(
            name='MentorActivity',
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
                ('name', models.CharField(max_length=31, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='Participant',
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
                ('user_id', models.IntegerField()),
                ('name', models.CharField(max_length=255)),
                (
                    'cell_phone',
                    phonenumber_field.modelfields.PhoneNumberField(
                        blank=True, max_length=128
                    ),
                ),
                ('last_updated', models.DateTimeField(auto_now=True)),
                (
                    'email',
                    models.EmailField(
                        help_text="This will be shared with leaders & other participants. <a href='/accounts/email/'>Manage email addresses</a>.",
                        max_length=254,
                        unique=True,
                    ),
                ),
                (
                    'affiliation',
                    models.CharField(
                        choices=[
                            (
                                'Undergraduate student',
                                [('MU', 'MIT undergrad'), ('NU', 'Non-MIT undergrad')],
                            ),
                            (
                                'Graduate student',
                                [
                                    ('MG', 'MIT grad student'),
                                    ('NG', 'Non-MIT grad student'),
                                ],
                            ),
                            ('MA', 'MIT affiliate'),
                            ('NA', 'Non-affiliate'),
                        ],
                        max_length=2,
                    ),
                ),
                (
                    'car',
                    ws.fields.OptionalOneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to='ws.Car',
                    ),
                ),
                ('discounts', models.ManyToManyField(blank=True, to='ws.Discount')),
                (
                    'emergency_info',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='ws.EmergencyInfo',
                    ),
                ),
            ],
            options={'ordering': ['name', 'email']},
        ),
        migrations.CreateModel(
            name='SignUp',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('notes', models.TextField(blank=True, max_length=1000)),
                ('order', models.IntegerField(blank=True, null=True)),
                ('manual_order', models.IntegerField(blank=True, null=True)),
                ('on_trip', models.BooleanField(default=False)),
                (
                    'participant',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
                    ),
                ),
            ],
            options={'ordering': ['manual_order', 'last_updated']},
        ),
        migrations.CreateModel(
            name='Trip',
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
                    'activity',
                    models.CharField(
                        choices=[
                            ('biking', 'Biking'),
                            ('boating', 'Boating'),
                            ('cabin', 'Cabin'),
                            ('climbing', 'Climbing'),
                            ('hiking', 'Hiking'),
                            ('winter_school', 'Winter School'),
                            ('circus', 'Circus'),
                            ('official_event', 'Official Event'),
                            ('course', 'Course'),
                        ],
                        default='winter_school',
                        max_length=31,
                    ),
                ),
                (
                    'allow_leader_signups',
                    models.BooleanField(
                        default=False,
                        help_text='Allow leaders to sign themselves up as trip leaders. (Leaders can always sign up as participants). Recommended for Circuses!',
                    ),
                ),
                ('name', models.CharField(max_length=127)),
                ('description', models.TextField()),
                (
                    'maximum_participants',
                    models.PositiveIntegerField(
                        default=8, verbose_name='Max participants'
                    ),
                ),
                ('difficulty_rating', models.CharField(max_length=63)),
                (
                    'level',
                    models.CharField(
                        blank=True,
                        help_text="This trip's A, B, or C designation (plus I/S rating if applicable).",
                        max_length=255,
                        null=True,
                    ),
                ),
                (
                    'prereqs',
                    models.CharField(
                        blank=True, max_length=255, verbose_name='Prerequisites'
                    ),
                ),
                ('chair_approved', models.BooleanField(default=False)),
                (
                    'notes',
                    models.TextField(
                        blank=True,
                        help_text='Participants must add notes to their signups if you complete this field. This is a great place to ask important questions.',
                        max_length=2000,
                    ),
                ),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_edited', models.DateTimeField(auto_now=True)),
                ('trip_date', models.DateField(default=ws.utils.dates.nearest_sat)),
                (
                    'signups_open_at',
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    'signups_close_at',
                    models.DateTimeField(
                        blank=True, default=ws.utils.dates.wed_morning, null=True
                    ),
                ),
                (
                    'let_participants_drop',
                    models.BooleanField(
                        default=False,
                        help_text='Allow participants to remove themselves from the trip any time before its start date.',
                    ),
                ),
                (
                    'honor_participant_pairing',
                    models.BooleanField(
                        default=True,
                        help_text='Try to place paired participants together on the trip.',
                    ),
                ),
                (
                    'algorithm',
                    models.CharField(
                        choices=[
                            ('lottery', 'lottery'),
                            ('fcfs', 'first-come, first-serve'),
                        ],
                        default='lottery',
                        max_length=31,
                    ),
                ),
                (
                    'lottery_task_id',
                    models.CharField(blank=True, max_length=36, null=True, unique=True),
                ),
                ('lottery_log', models.TextField(blank=True, null=True)),
                (
                    'creator',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='created_trips',
                        to='ws.Participant',
                    ),
                ),
            ],
            options={'ordering': ['-trip_date', '-time_created']},
        ),
        migrations.CreateModel(
            name='TripInfo',
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
                ('start_location', models.CharField(max_length=127)),
                ('start_time', models.CharField(max_length=63)),
                (
                    'turnaround_time',
                    models.CharField(
                        blank=True,
                        help_text="The time at which you'll turn back and head for your car/starting location",
                        max_length=63,
                    ),
                ),
                (
                    'return_time',
                    models.CharField(
                        help_text='When you expect to return to your car/starting location and be able to call the WIMP',
                        max_length=63,
                    ),
                ),
                (
                    'worry_time',
                    models.CharField(
                        help_text='Suggested: return time +3 hours. If the WIMP has not heard from you after this time and is unable to make contact with any leaders or participants, the authorities will be called.',
                        max_length=63,
                    ),
                ),
                (
                    'itinerary',
                    models.TextField(
                        help_text='A detailed account of your trip plan. Where will you be going? What route will you be taking? Include trails, peaks, intermediate destinations, back-up plans- anything that would help rescuers find you.'
                    ),
                ),
                (
                    'drivers',
                    models.ManyToManyField(
                        blank=True,
                        help_text="If a trip participant is driving, but is not on this list, they must first submit <a href='/profile/edit/#car'>information about their car</a>. They should then be added here.",
                        to='ws.Participant',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='WaitList',
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
                    'trip',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, to='ws.Trip'
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='WaitListSignup',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('manual_order', models.IntegerField(blank=True, null=True)),
                (
                    'signup',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE, to='ws.SignUp'
                    ),
                ),
                (
                    'waitlist',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to='ws.WaitList'
                    ),
                ),
            ],
            options={'ordering': ['-manual_order', 'time_created']},
        ),
        migrations.CreateModel(
            name='WinterSchoolLeaderApplication',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                (
                    'previous_rating',
                    models.CharField(
                        blank=True, help_text='Previous rating (if any)', max_length=255
                    ),
                ),
                (
                    'year',
                    models.PositiveIntegerField(
                        default=ws.utils.dates.ws_year,
                        help_text='Year this application pertains to.',
                        validators=[django.core.validators.MinValueValidator(2014)],
                    ),
                ),
                ('desired_rating', models.CharField(max_length=255)),
                (
                    'taking_wfa',
                    models.CharField(
                        choices=[
                            ('Yes', 'Yes'),
                            ('No', 'No'),
                            ('Maybe', "Maybe/don't know"),
                        ],
                        help_text='Save $100 on the course fee by leading two or more trips!',
                        max_length=10,
                        verbose_name='Do you plan on taking the subsidized WFA at MIT?',
                    ),
                ),
                (
                    'training',
                    models.TextField(
                        blank=True,
                        help_text='Details of any medical, technical, or leadership training and qualifications relevant to the winter environment. State the approximate dates of these activities. Leave blank if not applicable.',
                        max_length=5000,
                        verbose_name='Formal training and qualifications',
                    ),
                ),
                (
                    'winter_experience',
                    models.TextField(
                        blank=True,
                        help_text='Details of previous winter outdoors experience. Include the type of trip (x-country skiiing, above treeline, snowshoeing, ice climbing, etc), approximate dates and locations, numbers of participants, notable trail and weather conditions. Please also give details of whether you participated, led, or co-led these trips.',
                        max_length=5000,
                    ),
                ),
                (
                    'other_experience',
                    models.TextField(
                        blank=True,
                        help_text='Details about any relevant non-winter experience',
                        max_length=5000,
                        verbose_name='Other outdoors/leadership experience',
                    ),
                ),
                (
                    'notes_or_comments',
                    models.TextField(
                        blank=True,
                        help_text='Any relevant details, such as any limitations on availability on Tue/Thurs nights or weekends during IAP.',
                        max_length=5000,
                    ),
                ),
                (
                    'mentee_activities',
                    models.ManyToManyField(
                        blank=True,
                        help_text='Please select at least one.',
                        related_name='mentee_activities',
                        to='ws.MentorActivity',
                        verbose_name='For which activities would you like a mentor?',
                    ),
                ),
                (
                    'mentor_activities',
                    models.ManyToManyField(
                        blank=True,
                        help_text='Please select at least one.',
                        related_name='activities_mentored',
                        to='ws.MentorActivity',
                        verbose_name='Which activities would you like to mentor?',
                    ),
                ),
                (
                    'participant',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
                    ),
                ),
            ],
            options={'ordering': ['time_created'], 'abstract': False},
        ),
        migrations.CreateModel(
            name='WinterSchoolSettings',
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
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                (
                    'allow_setting_attendance',
                    models.BooleanField(
                        default=False,
                        verbose_name='Let participants set lecture attendance',
                    ),
                ),
                (
                    'last_updated_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to='ws.Participant',
                    ),
                ),
            ],
            options={'abstract': False},
        ),
        migrations.AddField(
            model_name='waitlist',
            name='unordered_signups',
            field=models.ManyToManyField(through='ws.WaitListSignup', to='ws.SignUp'),
        ),
        migrations.AddField(
            model_name='trip',
            name='info',
            field=ws.fields.OptionalOneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='ws.TripInfo',
            ),
        ),
        migrations.AddField(
            model_name='trip',
            name='leaders',
            field=models.ManyToManyField(
                blank=True, related_name='trips_led', to='ws.Participant'
            ),
        ),
        migrations.AddField(
            model_name='trip',
            name='signed_up_participants',
            field=models.ManyToManyField(through='ws.SignUp', to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='signup',
            name='trip',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Trip'
            ),
        ),
        migrations.AddField(
            model_name='lotteryinfo',
            name='paired_with',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='paired_by',
                to='ws.Participant',
            ),
        ),
        migrations.AddField(
            model_name='lotteryinfo',
            name='participant',
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
            ),
        ),
        migrations.AddField(
            model_name='lectureattendance',
            name='creator',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='lecture_attendances_marked',
                to='ws.Participant',
            ),
        ),
        migrations.AddField(
            model_name='lectureattendance',
            name='participant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
            ),
        ),
        migrations.AddField(
            model_name='leadersignup',
            name='participant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
            ),
        ),
        migrations.AddField(
            model_name='leadersignup',
            name='trip',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Trip'
            ),
        ),
        migrations.AddField(
            model_name='leaderrecommendation',
            name='creator',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='recommendations_created',
                to='ws.Participant',
            ),
        ),
        migrations.AddField(
            model_name='leaderrecommendation',
            name='participant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
            ),
        ),
        migrations.AddField(
            model_name='leaderrating',
            name='creator',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='ratings_created',
                to='ws.Participant',
            ),
        ),
        migrations.AddField(
            model_name='leaderrating',
            name='participant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
            ),
        ),
        migrations.AddField(
            model_name='hikingleaderapplication',
            name='participant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
            ),
        ),
        migrations.AddField(
            model_name='feedback',
            name='leader',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='authored_feedback',
                to='ws.Participant',
            ),
        ),
        migrations.AddField(
            model_name='feedback',
            name='participant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
            ),
        ),
        migrations.AddField(
            model_name='feedback',
            name='trip',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='ws.Trip',
            ),
        ),
        migrations.AddField(
            model_name='discount',
            name='administrators',
            field=models.ManyToManyField(
                blank=True,
                help_text='Persons selected to administer this discount',
                related_name='discounts_administered',
                to='ws.Participant',
            ),
        ),
        migrations.AddField(
            model_name='climbingleaderapplication',
            name='participant',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, to='ws.Participant'
            ),
        ),
    ]
