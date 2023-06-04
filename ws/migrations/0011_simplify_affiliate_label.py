# Generated by Django 1.11.16 on 2018-11-11 07:21

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ws', '0010_alumni_affiliation')]

    operations = [
        migrations.AlterField(
            model_name='participant',
            name='affiliation',
            field=models.CharField(
                max_length=2,
                choices=[
                    (
                        'Undergraduate student',
                        [('MU', 'MIT undergrad'), ('MU', 'Non-MIT undergrad')],
                    ),
                    (
                        'Graduate student',
                        [('MG', 'MIT grad student'), ('NG', 'Non-MIT grad student')],
                    ),
                    (
                        'MIT',
                        [
                            ('MA', 'MIT affiliate (staff or faculty)'),
                            ('ML', 'MIT alum (former student)'),
                        ],
                    ),
                    ('NA', 'Non-affiliate'),
                ],
            ),
        )
    ]
