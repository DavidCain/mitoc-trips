# Generated by Django 1.11.17 on 2018-12-23 02:05

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('ws', '0011_simplify_affiliate_label')]

    operations = [
        migrations.AlterField(
            model_name='participant',
            name='affiliation',
            field=models.CharField(
                max_length=2,
                choices=[
                    (
                        'Undergraduate student',
                        [('MU', 'MIT undergrad'), ('NU', 'Non-MIT undergrad')],
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
