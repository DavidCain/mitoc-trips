from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('ws', '0019_2020_ws_application')]

    operations = [
        migrations.AlterField(
            model_name='climbingleaderapplication',
            name='familiarity_spotting',
            field=models.CharField(
                choices=[
                    ('none', 'not at all'),
                    ('some', 'some exposure'),
                    ('comfortable', 'comfortable'),
                    ('very comfortable', 'very comfortable'),
                ],
                max_length=16,
                verbose_name='Familiarity with spotting boulder problems',
            ),
        ),
        migrations.AlterField(
            model_name='winterschoolleaderapplication',
            name='winter_experience',
            field=models.TextField(
                blank=True,
                help_text='Details of previous winter outdoors experience. '
                'Include the type of trip (x-country skiing, above treeline, snowshoeing, ice climbing, etc), '
                'approximate dates and locations, numbers of participants, notable trail and weather conditions. '
                'Please also give details of whether you participated, led, or co-led these trips.',
                max_length=5000,
            ),
        ),
    ]
