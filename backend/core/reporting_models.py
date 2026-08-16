from django.db import models
from django.utils import timezone as dj_timezone

from .models import TimestampedModel, User


class ReportDefinition(TimestampedModel):
    class DataSource(models.TextChoices):
        SHIFTS = 'shifts', 'Schichten'
        SHIFT_HISTORY = 'shift_history', 'Schicht-Historie'
        TIMES = 'times', 'Zeiterfassung'
        TIMESHEETS = 'timesheets', 'Timesheets'
        LABOR = 'labor', 'Personalkosten'

    name = models.CharField(max_length=180)
    data_source = models.CharField(max_length=30, choices=DataSource.choices)
    columns = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    sort = models.JSONField(default=list, blank=True)
    group_by = models.JSONField(default=list, blank=True)
    aggregates = models.JSONField(default=list, blank=True)
    shared = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='report_definitions')
    last_run_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['data_source', 'active'], name='report_def_source_idx')]


class ReportSchedule(TimestampedModel):
    class Frequency(models.TextChoices):
        DAILY = 'daily', 'Täglich'
        WEEKLY = 'weekly', 'Wöchentlich'
        MONTHLY = 'monthly', 'Monatlich'

    class FileFormat(models.TextChoices):
        CSV = 'csv', 'CSV'
        XLSX = 'xlsx', 'Excel XLSX'

    report = models.ForeignKey(ReportDefinition, on_delete=models.CASCADE, related_name='schedules')
    frequency = models.CharField(max_length=20, choices=Frequency.choices)
    file_format = models.CharField(max_length=10, choices=FileFormat.choices, default=FileFormat.CSV)
    recipients = models.JSONField(default=list, blank=True)
    local_hour = models.PositiveSmallIntegerField(default=8)
    weekday = models.PositiveSmallIntegerField(default=0)
    day_of_month = models.PositiveSmallIntegerField(default=1)
    timezone = models.CharField(max_length=64, default='Europe/Berlin')
    active = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(default=dj_timezone.now)
    last_run_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='report_schedules')

    class Meta:
        ordering = ['next_run_at']
        indexes = [models.Index(fields=['active', 'next_run_at'], name='report_schedule_due_idx')]


class ReportRun(TimestampedModel):
    class Trigger(models.TextChoices):
        MANUAL = 'manual', 'Manuell'
        SCHEDULED = 'scheduled', 'Geplant'

    class Status(models.TextChoices):
        RUNNING = 'running', 'Läuft'
        SUCCESS = 'success', 'Erfolgreich'
        FAILED = 'failed', 'Fehlgeschlagen'

    report = models.ForeignKey(ReportDefinition, on_delete=models.SET_NULL, null=True, blank=True, related_name='runs')
    schedule = models.ForeignKey(ReportSchedule, on_delete=models.SET_NULL, null=True, blank=True, related_name='runs')
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='report_runs')
    trigger = models.CharField(max_length=20, choices=Trigger.choices, default=Trigger.MANUAL)
    file_format = models.CharField(max_length=10, choices=ReportSchedule.FileFormat.choices, default=ReportSchedule.FileFormat.CSV)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    row_count = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)
    filters_snapshot = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'], name='report_run_status_idx')]
