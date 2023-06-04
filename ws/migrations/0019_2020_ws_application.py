from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ws', '0018_participant_password_last_checked')]

    operations = [
        migrations.AlterField(
            model_name='winterschoolleaderapplication',
            name='taking_wfa',
            field=models.CharField(
                choices=[('Yes', 'Yes'), ('No', 'No'), ('Maybe', "Maybe/don't know")],
                help_text="You can subsidize your WFA certification by $100 by leading two or more trips! We will be holding a WFA course on MIT's campus (dates to be announced soon).",
                max_length=10,
                verbose_name='Do you plan on taking a WFA course before Winter School?',
            ),
        ),
        migrations.AddField(
            model_name='winterschoolleaderapplication',
            name='technical_skills',
            field=models.TextField(
                blank=True,
                help_text='Please summarize how you meet the criteria for the leader rating you are requesting, including any relevant technical skills (traction use, navigation, use of overnight equipment, etc.)',
                max_length=5000,
            ),
        ),
        migrations.AddField(
            model_name='winterschoolleaderapplication',
            name='ice_experience',
            field=models.TextField(
                blank=True,
                help_text='Please describe your ice-climbing experience, including the approximate number of days you have ice-climbed in the last two years.',
                max_length=5000,
                verbose_name='Ice-climbing experience (ice leader applicants only)',
            ),
        ),
        migrations.AddField(
            model_name='winterschoolleaderapplication',
            name='ski_experience',
            field=models.TextField(
                blank=True,
                help_text='Please describe your skiing experience, including both resort and back-country experience, and an estimate of the number of days you have backcountry skied in the last two years.',
                max_length=5000,
                verbose_name='Ski experience (ski leader applicants only)',
            ),
        ),
        migrations.AddField(
            model_name='winterschoolleaderapplication',
            name='mentorship_goals',
            field=models.TextField(
                blank=True,
                help_text='What are you looking to get out of the mentorship program?',
                max_length=5000,
            ),
        ),
    ]
