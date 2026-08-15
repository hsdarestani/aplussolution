import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0011_attendance_v4'),
    ]

    operations = [
        migrations.CreateModel(
            name='PayPeriod',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=160)),
                ('starts_on', models.DateField()),
                ('ends_on', models.DateField()),
                ('status', models.CharField(choices=[('open', 'Offen'), ('review', 'In Prüfung'), ('closed', 'Geschlossen'), ('locked', 'Gesperrt')], default='open', max_length=20)),
                ('currency', models.CharField(default='EUR', max_length=3)),
                ('notes', models.TextField(blank=True)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('locked_at', models.DateTimeField(blank=True, null=True)),
                ('reopen_count', models.PositiveIntegerField(default=0)),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pay_periods_closed', to=settings.AUTH_USER_MODEL)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pay_periods_created', to=settings.AUTH_USER_MODEL)),
                ('locked_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pay_periods_locked', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-starts_on', '-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='payperiod',
            constraint=models.UniqueConstraint(fields=('starts_on', 'ends_on'), name='pay_period_unique_range'),
        ),
        migrations.AddConstraint(
            model_name='payperiod',
            constraint=models.CheckConstraint(condition=models.Q(ends_on__gte=models.F('starts_on')), name='pay_period_valid_range'),
        ),
        migrations.AddIndex(
            model_name='payperiod',
            index=models.Index(fields=['status', 'starts_on', 'ends_on'], name='pay_period_status_idx'),
        ),
        migrations.CreateModel(
            name='WorkerTimesheet',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('open', 'Offen'), ('submitted', 'Eingereicht'), ('approved', 'Freigegeben'), ('reopened', 'Wieder geöffnet'), ('locked', 'Gesperrt')], default='open', max_length=20)),
                ('gross_minutes', models.PositiveIntegerField(default=0)),
                ('paid_break_minutes', models.PositiveIntegerField(default=0)),
                ('unpaid_break_minutes', models.PositiveIntegerField(default=0)),
                ('net_minutes', models.PositiveIntegerField(default=0)),
                ('gross_estimate', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('entry_count', models.PositiveIntegerField(default=0)),
                ('exception_count', models.PositiveIntegerField(default=0)),
                ('blocking_exception_count', models.PositiveIntegerField(default=0)),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('approved_at', models.DateTimeField(blank=True, null=True)),
                ('locked_at', models.DateTimeField(blank=True, null=True)),
                ('review_note', models.TextField(blank=True)),
                ('revision', models.PositiveIntegerField(default=1)),
                ('approved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='timesheets_approved', to=settings.AUTH_USER_MODEL)),
                ('pay_period', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='timesheets', to='core.payperiod')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='worker_timesheets', to='core.workerprofile')),
            ],
            options={'ordering': ['worker__employee_number']},
        ),
        migrations.AddConstraint(
            model_name='workertimesheet',
            constraint=models.UniqueConstraint(fields=('pay_period', 'worker'), name='timesheet_period_worker_unique'),
        ),
        migrations.AddIndex(
            model_name='workertimesheet',
            index=models.Index(fields=['pay_period', 'status'], name='timesheet_period_status_idx'),
        ),
        migrations.CreateModel(
            name='TimesheetEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('clock_in', models.DateTimeField()),
                ('clock_out', models.DateTimeField(blank=True, null=True)),
                ('gross_minutes', models.PositiveIntegerField(default=0)),
                ('paid_break_minutes', models.PositiveIntegerField(default=0)),
                ('unpaid_break_minutes', models.PositiveIntegerField(default=0)),
                ('net_minutes', models.PositiveIntegerField(default=0)),
                ('hourly_rate', models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ('amount_estimate', models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ('review_status', models.CharField(choices=[('pending', 'Offen'), ('approved', 'Freigegeben'), ('rejected', 'Abgelehnt')], default='pending', max_length=20)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('review_note', models.TextField(blank=True)),
                ('locked', models.BooleanField(default=False)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='timesheet_entries_reviewed', to=settings.AUTH_USER_MODEL)),
                ('time_entry', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='timesheet_snapshot', to='core.timeentry')),
                ('timesheet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entries', to='core.workertimesheet')),
            ],
            options={'ordering': ['clock_in']},
        ),
        migrations.AddIndex(
            model_name='timesheetentry',
            index=models.Index(fields=['timesheet', 'review_status'], name='timesheet_entry_review_idx'),
        ),
        migrations.CreateModel(
            name='TimesheetException',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('exception_type', models.CharField(choices=[('missing_entry', 'Zeiteintrag fehlt'), ('running_entry', 'Timer läuft'), ('unapproved_entry', 'Zeiteintrag nicht freigegeben'), ('rejected_entry', 'Zeiteintrag abgelehnt'), ('attendance_notice', 'Attendance-Hinweis offen')], max_length=30)),
                ('severity', models.CharField(choices=[('info', 'Hinweis'), ('warning', 'Warnung'), ('blocking', 'Blockierend')], default='warning', max_length=20)),
                ('status', models.CharField(choices=[('open', 'Offen'), ('resolved', 'Erledigt'), ('dismissed', 'Verworfen')], default='open', max_length=20)),
                ('dedupe_key', models.CharField(max_length=220, unique=True)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('resolution_note', models.TextField(blank=True)),
                ('attendance_notice', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='timesheet_exceptions', to='core.attendancenotice')),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='timesheet_exceptions_resolved', to=settings.AUTH_USER_MODEL)),
                ('shift', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='timesheet_exceptions', to='core.shift')),
                ('time_entry', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='timesheet_exceptions', to='core.timeentry')),
                ('timesheet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exceptions', to='core.workertimesheet')),
            ],
            options={'ordering': ['-severity', '-created_at']},
        ),
        migrations.AddIndex(
            model_name='timesheetexception',
            index=models.Index(fields=['timesheet', 'status', 'severity'], name='timesheet_exception_idx'),
        ),
        migrations.AddIndex(
            model_name='timesheetexception',
            index=models.Index(fields=['exception_type', 'status'], name='timesheet_exception_type_idx'),
        ),
    ]
