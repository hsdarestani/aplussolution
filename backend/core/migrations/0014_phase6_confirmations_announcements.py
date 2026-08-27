import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0013_scope_workforce_master_data')]

    operations = [
        migrations.AddField(
            model_name='shift',
            name='confirmation_required',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='shiftslot',
            name='confirmation_status',
            field=models.CharField(
                choices=[('pending', 'Ausstehend'), ('confirmed', 'Bestätigt'), ('rejected', 'Abgelehnt')],
                default='confirmed', max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='shiftslot',
            name='confirmation_requested_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='shiftslot',
            name='confirmation_decided_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='Announcement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(default='Mitteilung', max_length=200)),
                ('body', models.TextField(blank=True)),
                ('attachment', models.FileField(blank=True, null=True, upload_to='announcements/%Y/%m/')),
                ('sent_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_announcements', to='core.user')),
            ],
            options={'ordering': ['-sent_at', '-created_at']},
        ),
        migrations.CreateModel(
            name='AnnouncementRecipient',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('announcement', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recipient_links', to='core.announcement')),
                ('notification', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='announcement_links', to='core.notification')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='announcement_links', to='core.user')),
            ],
            options={'ordering': ['created_at'], 'unique_together': {('announcement', 'user')}},
        ),
        migrations.AddField(
            model_name='announcement',
            name='recipients',
            field=models.ManyToManyField(related_name='received_announcements', through='core.AnnouncementRecipient', to='core.user'),
        ),
    ]
