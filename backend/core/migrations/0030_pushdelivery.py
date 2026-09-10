import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0029_send_spenerhaus_housekeeping_notifications'),
    ]

    operations = [
        migrations.CreateModel(
            name='PushDelivery',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('device', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='core.pushdevice')),
                ('notification', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='push_deliveries', to='core.notification')),
            ],
            options={
                'ordering': ['-created_at'],
                'constraints': [
                    models.UniqueConstraint(fields=('notification', 'device'), name='core_push_delivery_unique'),
                ],
            },
        ),
    ]
