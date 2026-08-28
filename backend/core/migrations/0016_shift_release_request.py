import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0015_shift_visibility_preferences')]

    operations = [
        migrations.CreateModel(
            name='ShiftReleaseRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending', 'Offen'), ('approved', 'Genehmigt'), ('rejected', 'Abgelehnt'), ('cancelled', 'Storniert')], default='pending', max_length=20)),
                ('decision_note', models.TextField(blank=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='release_requests_decided', to=settings.AUTH_USER_MODEL)),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='release_requests', to='core.shift')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shift_release_requests', to='core.workerprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='shiftreleaserequest',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'pending')), fields=('shift', 'worker'), name='unique_pending_shift_release'),
        ),
    ]
