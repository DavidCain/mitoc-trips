# Generated by Django 4.2.11 on 2024-04-23 01:21

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ws", "0003_membershipstats"),
    ]

    operations = [
        migrations.AlterField(
            model_name="leaderrating",
            name="active",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.AlterField(
            model_name="signup",
            name="on_trip",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
