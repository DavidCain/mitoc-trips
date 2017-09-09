# -*- coding: utf-8 -*-

import datetime

import localflavor.us.models

from django.conf import settings
from django.db import migrations, models
import django.utils.timezone
from django.utils.timezone import utc
import django.core.validators

import ws.fields
import ws.utils.dates


class Migration(migrations.Migration):

    replaces = [
        ('ws', '0001_initial'),
        ('ws', '0002_auto_20141031_1643'),
        ('ws', '0003_auto_20141103_1440'),
        ('ws', '0005_trip_worry_time'),
        ('ws', '0006_auto_20150106_1950'),
        ('ws', '0007_auto_20150107_0033'),
        ('ws', '0008_auto_20150126_0903'),
        ('ws', '0009_auto_20150127_1752'),
        ('ws', '0010_remove_leaders_20151026_2106'),
        ('ws', '0011_change_ratings_20151026_2150'),
        ('ws', '0012_auto_20151026_2207'),
        ('ws', '0013_remove_leaders_20151026_2233'),
        ('ws', '0014_trip_activity'),
        ('ws', '0015_auto_20151128_1717'),
        ('ws', '0016_rename_emergency_contact_fields'),
        ('ws', '0017_clarify_participant_email'),
        ('ws', '0018_sort_trip_signups'),
        ('ws', '0019_trip_level_20160118_2018'),
        ('ws', '0020_new_activity_types'),
        ('ws', '0021_restore_econtact_names_20160227_1345'),
        ('ws', '0001_squashed_0021_restore_econtact_names_20160227_1345')
    ]

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Car',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('license_plate', models.CharField(max_length=31, validators=[django.core.validators.RegexValidator('^[a-zA-Z0-9 ]*$', 'Only alphanumeric characters and spaces allowed')])),
                ('state', localflavor.us.models.USStateField(max_length=2)),
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
                ('drivers', models.ManyToManyField(help_text="If a trip participant is driving, but is not on this list, they must first submit <a href='/profile/edit/#car'>information about their car</a>. They should then be added here.", to='ws.Participant', blank=True)),
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
        migrations.AlterField(
            model_name='trip',
            name='level',
            field=models.CharField(help_text="This trip's A, B, or C designation (plus I/S rating if applicable).", max_length=255, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='trip',
            name='allow_leader_signups',
            field=models.BooleanField(default=False, help_text='Allow leaders (with ratings for this activity) to sign themselves up for the trip any time before its date. Recommended for Circuses!'),
        ),
        migrations.CreateModel(
            name='LeaderSignUp',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('notes', models.TextField(max_length=1000, blank=True)),
                ('participant', models.ForeignKey(to='ws.Participant')),
                ('trip', models.ForeignKey(to='ws.Trip')),
            ],
            options={
                'ordering': ['time_created'],
            },
        ),
        migrations.AlterField(
            model_name='trip',
            name='description',
            field=models.TextField(help_text='Markdown accepted here!'),
        ),
        migrations.AlterField(
            model_name='trip',
            name='notes',
            field=models.TextField(help_text='Participants must add notes to their signups if you complete this field. This is a great place to ask important questions. (Markdown accepted here!)', max_length=2000, blank=True),
        ),
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
        migrations.AlterField(
            model_name='trip',
            name='description',
            field=models.TextField(),
        ),
        migrations.AlterField(
            model_name='trip',
            name='notes',
            field=models.TextField(help_text='Participants must add notes to their signups if you complete this field. This is a great place to ask important questions.', max_length=2000, blank=True),
        ),
        migrations.AddField(
            model_name='trip',
            name='let_participants_drop',
            field=models.BooleanField(default=False, help_text='Allow participants to remove themselves from the trip any time before its start date.'),
        ),
        migrations.AlterField(
            model_name='trip',
            name='maximum_participants',
            field=models.PositiveIntegerField(default=8, verbose_name='Max participants'),
        ),
        migrations.AlterField(
            model_name='trip',
            name='prereqs',
            field=models.CharField(max_length=255, verbose_name='Prerequisites', blank=True),
        ),
        migrations.AlterField(
            model_name='participant',
            name='email',
            field=models.EmailField(help_text="This will be shared with leaders & other participants. <a href='/accounts/email/'>Manage email addresses</a>.", unique=True, max_length=254),
        ),
        migrations.AlterField(
            model_name='trip',
            name='leaders',
            field=models.ManyToManyField(related_name='trips_led', to='ws.Participant', blank=True),
        ),
        migrations.AddField(
            model_name='trip',
            name='lottery_task_id',
            field=models.CharField(max_length='36', unique=True, null=True, blank=True),
        ),
        migrations.AddField(
            model_name='leaderrating',
            name='active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='leaderrating',
            name='creator',
            field=models.ForeignKey(related_name='ratings_created', default=1, to='ws.Participant'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='leaderrating',
            name='time_created',
            field=models.DateTimeField(default=datetime.datetime(2014, 1, 1, 0, 0, tzinfo=utc), auto_now_add=True),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='leaderapplication',
            name='participant',
            field=models.ForeignKey(to='ws.Participant'),
        ),
        migrations.AddField(
            model_name='leaderapplication',
            name='year',
            field=models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Winter School year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)]),
        ),
        migrations.AddField(
            model_name='leaderapplication',
            name='activity',
            field=models.CharField(default='winter_school', max_length='31', choices=[('biking', 'Biking'), ('boating', 'Boating'), ('cabin', 'Cabin'), ('climbing', 'Climbing'), ('hiking', 'Hiking'), ('winter_school', 'Winter School'), ('circus', 'Circus'), ('official_event', 'Official Event'), ('course', 'Course')]),
        ),
        migrations.CreateModel(
            name='LeaderRecommendation',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('activity', models.CharField(max_length='31', choices=[('biking', 'Biking'), ('boating', 'Boating'), ('cabin', 'Cabin'), ('climbing', 'Climbing'), ('hiking', 'Hiking'), ('winter_school', 'Winter School'), ('circus', 'Circus'), ('official_event', 'Official Event'), ('course', 'Course')])),
                ('rating', models.CharField(max_length=31)),
                ('notes', models.TextField(max_length=500, blank=True)),
                ('creator', models.ForeignKey(related_name='recommendations_created', to='ws.Participant')),
                ('participant', models.ForeignKey(to='ws.Participant')),
            ],
            options={
                'ordering': ['participant'],
                'abstract': False,
            },
        ),
        migrations.RunSQL(
            sql="\n    UPDATE django_content_type\n       SET model = 'winterschoolleaderapplication'\n     WHERE app_label = 'ws' AND\n           model = 'leaderapplication';\n\n",
            reverse_sql="\n    UPDATE django_content_type\n       SET model = 'leaderapplication'\n     WHERE model = 'winterschoolleaderapplication' AND\n           label = 'ws';\n",
        ),
        migrations.RenameModel(
            old_name='LeaderApplication',
            new_name='WinterSchoolLeaderApplication',
        ),
        migrations.AlterModelOptions(
            name='winterschoolleaderapplication',
            options={'ordering': ['time_created']},
        ),
        migrations.RemoveField(
            model_name='winterschoolleaderapplication',
            name='activity',
        ),
        migrations.AlterField(
            model_name='winterschoolleaderapplication',
            name='year',
            field=models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)]),
        ),
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
        migrations.CreateModel(
            name='LectureAttendance',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('year', models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Winter School year when lectures were attended.', validators=[django.core.validators.MinValueValidator(2016)])),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('participant', models.ForeignKey(to='ws.Participant')),
                ('creator', models.ForeignKey(related_name='lecture_attendances_marked', to='ws.Participant')),
            ],
        ),
        migrations.AlterField(
            model_name='car',
            name='year',
            field=models.PositiveIntegerField(validators=[django.core.validators.MaxValueValidator(2019), django.core.validators.MinValueValidator(1903)]),
        ),
        migrations.RemoveField(
            model_name='participant',
            name='attended_lectures',
        ),
        migrations.CreateModel(
            name='WinterSchoolSettings',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('allow_setting_attendance', models.BooleanField(default=False, verbose_name='Let participants set lecture attendance')),
                ('last_updated_by', models.ForeignKey(blank=True, to='ws.Participant', null=True)),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AlterField(
            model_name='participant',
            name='affiliation',
            field=models.CharField(max_length=2, choices=[('Undergraduate student', [('MU', 'MIT undergrad'), ('NU', 'Non-MIT undergrad')]), ('Graduate student', [('MG', 'MIT grad student'), ('NG', 'Non-MIT grad student')]), ('MA', 'MIT affiliate'), ('NA', 'Non-affiliate')]),
        ),
        migrations.RenameField(
            model_name='trip',
            old_name='wsc_approved',
            new_name='chair_approved',
        ),
        migrations.AlterField(
            model_name='winterschoolleaderapplication',
            name='year',
            field=models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)]),
        ),
        migrations.AlterField(
            model_name='lotteryinfo',
            name='car_status',
            field=models.CharField(default='none', max_length=7, choices=[('none', 'Not driving'), ('own', 'Can drive own car'), ('rent', 'Willing to rent')]),
        ),
        migrations.AddField(
            model_name='discount',
            name='report_leader',
            field=models.BooleanField(default=False, help_text='Report MITOC leader status to discount provider'),
        ),
        migrations.AddField(
            model_name='discount',
            name='student_required',
            field=models.BooleanField(default=False, help_text='Discount provider requires recipients to be students'),
        ),
        migrations.AddField(
            model_name='discount',
            name='report_access',
            field=models.BooleanField(default=False, help_text='Report if participant should have leader, student, or admin level access'),
        ),
        migrations.AddField(
            model_name='discount',
            name='administrators',
            field=models.ManyToManyField(help_text='Persons selected to administer this discount', related_name='discounts_administered', to='ws.Participant', blank=True),
        ),
        migrations.AddField(
            model_name='discount',
            name='report_student',
            field=models.BooleanField(default=False, help_text='Report MIT affiliation and student status to discount provider'),
        ),
        migrations.AddField(
            model_name='discount',
            name='report_school',
            field=models.BooleanField(default=False, help_text='Report MIT affiliation if participant is a student'),
        ),
        migrations.CreateModel(
            name='ClimbingLeaderApplication',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('time_created', models.DateTimeField(auto_now_add=True)),
                ('previous_rating', models.CharField(help_text='Previous rating (if any)', max_length=255, blank=True)),
                ('year', models.PositiveIntegerField(default=ws.utils.dates.ws_year, help_text='Year this application pertains to.', validators=[django.core.validators.MinValueValidator(2014)])),
                ('desired_rating', models.CharField(max_length=32, choices=[('Bouldering', 'Bouldering'), ('Single-pitch', 'Single-pitch'), ('Multi-pitch', 'Multi-pitch'), ('Bouldering + Single-pitch', 'Bouldering + Single-pitch'), ('Bouldering + Multi-pitch', 'Bouldering + Multi-pitch')])),
                ('years_climbing', models.IntegerField()),
                ('years_climbing_outside', models.IntegerField()),
                ('outdoor_bouldering_grade', models.CharField(help_text='At what grade are you comfortable bouldering outside?', max_length=255)),
                ('outdoor_sport_leading_grade', models.CharField(help_text='At what grade are you comfortable leading outside on sport routes?', max_length=255)),
                ('outdoor_trad_leading_grade', models.CharField(help_text='At what grade are you comfortable leading outside on trad routes?', max_length=255)),
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
        migrations.AddField(
            model_name='trip',
            name='lottery_log',
            field=models.TextField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='trip',
            name='honor_participant_pairing',
            field=models.BooleanField(default=True, help_text='Try to place paired participants together on the trip.'),
        ),
        migrations.AlterField(
            model_name='trip',
            name='allow_leader_signups',
            field=models.BooleanField(default=False, help_text='Allow leaders to sign themselves up as trip leaders. (Leaders can always sign up as participants). Recommended for Circuses!'),
        ),
        migrations.AddField(
            model_name='discount',
            name='active',
            field=models.BooleanField(default=True, help_text='Discount is currently open & active'),
        ),
    ]
