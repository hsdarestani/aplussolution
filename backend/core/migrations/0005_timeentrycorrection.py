import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0004_portalinvitation')]

    operations = [
        migrations.CreateModel(
            name='TimeEntryCorrection',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('requested_clock_in', models.DateTimeField(blank=True, null=True)),
                ('requested_clock_out', models.DateTimeField(blank=True, null=True)),
                ('reason', models.TextField()),
                ('status', models.CharField(choices=[('pending', 'Offen'), ('approved', 'Genehmigt'), ('rejected', 'Abgelehnt'), ('cancelled', 'Zurückgezogen')], default='pending', max_length=20)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('decision_note', models.TextField(blank=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='decided_time_corrections', to='core.user')),
                ('entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='correction_requests', to='core.timeentry')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='time_correction_requests', to='core.workerprofile')),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
