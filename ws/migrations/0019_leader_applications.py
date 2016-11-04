# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations


name_ws = """
    UPDATE django_content_type
       SET model = 'winterschoolleaderapplication'
     WHERE app_label = 'ws' AND
           model = 'leaderapplication';

"""

unname_ws = """
    UPDATE django_content_type
       SET model = 'leaderapplication'
     WHERE model = 'winterschoolleaderapplication' AND
           label = 'ws';
"""


class Migration(migrations.Migration):
    """ Rename the content type before renaming models so we get persistence. """

    dependencies = [
        ('ws', '0018_leaderrecommendation'),
    ]

    operations = [
        migrations.RunSQL(name_ws, unname_ws),
    ]
