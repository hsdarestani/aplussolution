import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0003_shiftassignment')]

    operations = [
        migrations.CreateModel(
            name='PortalInvitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('token_hash', models.CharField(max_length=64, unique=True)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('delivery_channel', models.CharField(blank=True, max_length=30)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_portal_invitations', to='core.user')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='portal_invitations', to='core.user')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', 'used_at', 'expires_at'], name='core_portal_user_id_9034ec_idx')],
            },
        ),
    ]
