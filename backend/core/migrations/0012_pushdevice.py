import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0011_archive_historical_wiw_time_entries'),
    ]

    operations = [
        migrations.CreateModel(
            name='PushDevice',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('platform', models.CharField(choices=[('android', 'Android'), ('ios', 'iOS')], max_length=20)),
                ('token', models.TextField(unique=True)),
                ('app_id', models.CharField(default='de.aplussolution.workforce', max_length=180)),
                ('device_name', models.CharField(blank=True, max_length=200)),
                ('active', models.BooleanField(default=True)),
                ('last_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_error', models.TextField(blank=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='push_devices', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-last_seen_at']},
        ),
        migrations.AddIndex(
            model_name='pushdevice',
            index=models.Index(fields=['user', 'active'], name='core_push_u_active_idx'),
        ),
        migrations.AddIndex(
            model_name='pushdevice',
            index=models.Index(fields=['platform', 'active'], name='core_push_p_active_idx'),
        ),
    ]
