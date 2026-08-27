from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0014_phase6_confirmations_announcements')]

    operations = [
        migrations.AddField(
            model_name='workerprofile',
            name='open_shift_client_ids',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='workerprofile',
            name='schedule_groups',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='shift',
            name='schedule_groups',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
