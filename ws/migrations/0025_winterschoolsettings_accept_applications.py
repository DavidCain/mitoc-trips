from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [('ws', '0024_signups_close_at')]

    operations = [
        migrations.AddField(
            model_name='winterschoolsettings',
            name='accept_applications',
            field=models.BooleanField(
                default=True,
                verbose_name='Accept new Winter School leader applications',
            ),
        )
    ]
