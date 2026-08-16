import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0008_wiw_premium_parity')]

    operations = [
        migrations.CreateModel(
            name='ShiftPickupRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending', 'Offen'), ('approved', 'Genehmigt'), ('rejected', 'Abgelehnt'), ('cancelled', 'Storniert')], default='pending', max_length=20)),
                ('decision_note', models.TextField(blank=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pickup_requests_decided', to=settings.AUTH_USER_MODEL)),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pickup_requests', to='core.shift')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pickup_requests', to='core.workerprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='shiftpickuprequest',
            constraint=models.UniqueConstraint(condition=models.Q(('status', 'pending')), fields=('shift', 'worker'), name='unique_pending_shift_pickup'),
        ),
        migrations.CreateModel(
            name='WorkerLocationMembership',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('home', models.BooleanField(default=False)), ('active', models.BooleanField(default=True)),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='worker_memberships', to='core.location')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='location_memberships', to='core.workerprofile')),
            ],
            options={'ordering': ['worker__employee_number', '-home', 'location__name'], 'unique_together': {('worker', 'location')}},
        ),
    ]
