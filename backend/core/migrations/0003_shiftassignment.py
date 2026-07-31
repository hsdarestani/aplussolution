import uuid

import django.db.models.deletion
from django.db import migrations, models


def migrate_legacy_shifts(apps, schema_editor):
    Shift = apps.get_model('core', 'Shift')
    Assignment = apps.get_model('core', 'ShiftAssignment')
    for shift in Shift.objects.all().iterator():
        count = max(1, int(shift.required_count or 1))
        for index in range(count):
            worker_id = shift.worker_id if index == 0 and shift.worker_id else None
            Assignment.objects.create(
                shift_id=shift.id,
                worker_id=worker_id,
                status='claimed' if worker_id else 'open',
                source='migration',
                wiw_shift_id=shift.wiw_shift_id if index == 0 and shift.wiw_shift_id else None,
            )


def reverse_legacy_shifts(apps, schema_editor):
    Shift = apps.get_model('core', 'Shift')
    Assignment = apps.get_model('core', 'ShiftAssignment')
    for shift in Shift.objects.all().iterator():
        claimed = Assignment.objects.filter(shift_id=shift.id, status='claimed', worker_id__isnull=False).first()
        shift.worker_id = claimed.worker_id if claimed and int(shift.required_count or 1) == 1 else None
        shift.save(update_fields=['worker'])


class Migration(migrations.Migration):
    dependencies = [('core', '0002_repair_legacy_schema')]

    operations = [
        migrations.CreateModel(
            name='ShiftAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('open', 'Offen'), ('claimed', 'Übernommen'), ('cancelled', 'Storniert')], default='open', max_length=20)),
                ('source', models.CharField(choices=[('system', 'System'), ('worker_claim', 'Mitarbeiter'), ('worker_release', 'Zurück in Pool'), ('admin_override', 'Admin-Override'), ('wiw', 'When I Work'), ('migration', 'Migration')], default='system', max_length=30)),
                ('wiw_shift_id', models.CharField(blank=True, max_length=80, null=True, unique=True)),
                ('claimed_at', models.DateTimeField(blank=True, null=True)),
                ('released_at', models.DateTimeField(blank=True, null=True)),
                ('note', models.TextField(blank=True)),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='core.shift')),
                ('worker', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shift_assignments', to='core.workerprofile')),
            ],
            options={
                'ordering': ['shift__starts_at', 'created_at'],
                'indexes': [
                    models.Index(fields=['shift', 'status'], name='core_shifta_shift_i_53e25e_idx'),
                    models.Index(fields=['worker', 'status'], name='core_shifta_worker__016a11_idx'),
                ],
            },
        ),
        migrations.RunPython(migrate_legacy_shifts, reverse_legacy_shifts),
    ]
