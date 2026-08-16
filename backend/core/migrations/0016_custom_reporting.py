import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0015_premium_integrations')]

    operations = [
        migrations.CreateModel(
            name='ReportDefinition',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=180)),
                ('data_source', models.CharField(choices=[('shifts', 'Schichten'), ('shift_history', 'Schicht-Historie'), ('times', 'Zeiterfassung'), ('timesheets', 'Timesheets'), ('labor', 'Personalkosten')], max_length=30)),
                ('columns', models.JSONField(blank=True, default=list)),
                ('filters', models.JSONField(blank=True, default=dict)),
                ('sort', models.JSONField(blank=True, default=list)),
                ('group_by', models.JSONField(blank=True, default=list)),
                ('aggregates', models.JSONField(blank=True, default=list)),
                ('shared', models.BooleanField(default=False)),
                ('active', models.BooleanField(default=True)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='report_definitions', to='core.user')),
            ],
            options={'ordering': ['name'], 'indexes': [models.Index(fields=['data_source', 'active'], name='report_def_source_idx')]},
        ),
        migrations.CreateModel(
            name='ReportSchedule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('frequency', models.CharField(choices=[('daily', 'Täglich'), ('weekly', 'Wöchentlich'), ('monthly', 'Monatlich')], max_length=20)),
                ('file_format', models.CharField(choices=[('csv', 'CSV'), ('xlsx', 'Excel XLSX')], default='csv', max_length=10)),
                ('recipients', models.JSONField(blank=True, default=list)),
                ('local_hour', models.PositiveSmallIntegerField(default=8)),
                ('weekday', models.PositiveSmallIntegerField(default=0)),
                ('day_of_month', models.PositiveSmallIntegerField(default=1)),
                ('timezone', models.CharField(default='Europe/Berlin', max_length=64)),
                ('active', models.BooleanField(default=True)),
                ('next_run_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='report_schedules', to='core.user')),
                ('report', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='core.reportdefinition')),
            ],
            options={'ordering': ['next_run_at'], 'indexes': [models.Index(fields=['active', 'next_run_at'], name='report_schedule_due_idx')]},
        ),
        migrations.CreateModel(
            name='ReportRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('trigger', models.CharField(choices=[('manual', 'Manuell'), ('scheduled', 'Geplant')], default='manual', max_length=20)),
                ('file_format', models.CharField(choices=[('csv', 'CSV'), ('xlsx', 'Excel XLSX')], default='csv', max_length=10)),
                ('status', models.CharField(choices=[('running', 'Läuft'), ('success', 'Erfolgreich'), ('failed', 'Fehlgeschlagen')], default='running', max_length=20)),
                ('row_count', models.PositiveIntegerField(default=0)),
                ('checksum', models.CharField(blank=True, max_length=64)),
                ('filters_snapshot', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('report', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='runs', to='core.reportdefinition')),
                ('requested_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='report_runs', to='core.user')),
                ('schedule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='runs', to='core.reportschedule')),
            ],
            options={'ordering': ['-created_at'], 'indexes': [models.Index(fields=['status', 'created_at'], name='report_run_status_idx')]},
        ),
    ]
