# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ws', '0032_climbingleaderapplication'),
    ]

    operations = [
        migrations.RenameField(
            model_name='climbingleaderapplication',
            old_name='outdoor_bouldering_level',
            new_name='outdoor_bouldering_grade',
        ),
        migrations.RenameField(
            model_name='climbingleaderapplication',
            old_name='outdoor_sport_leading_level',
            new_name='outdoor_sport_leading_grade',
        ),
        migrations.RenameField(
            model_name='climbingleaderapplication',
            old_name='outdoor_trad_leading_level',
            new_name='outdoor_trad_leading_grade',
        ),
        migrations.AlterField(
            model_name='climbingleaderapplication',
            name='outdoor_bouldering_grade',
            field=models.CharField(help_text='At what grade are you comfortable bouldering outside?', max_length=255),
        ),
        migrations.AlterField(
            model_name='climbingleaderapplication',
            name='outdoor_sport_leading_grade',
            field=models.CharField(help_text='At what grade are you comfortable leading outside on sport routes?', max_length=255),
        ),
        migrations.AlterField(
            model_name='climbingleaderapplication',
            name='outdoor_trad_leading_grade',
            field=models.CharField(help_text='At what grade are you comfortable leading outside on trad routes?', max_length=255),
        ),
    ]
