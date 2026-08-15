from django.db import models
from django.utils import timezone

from .models import Shift, TimeEntry, TimestampedModel, User, WorkerProfile


class PayPeriod(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Offen'
        REVIEW = 'review', 'In Prüfung'
        CLOSED = 'closed', 'Geschlossen'
        LOCKED = 'locked', 'Gesperrt'

    name = models.CharField(max_length=160)
    starts_on = models.DateField()
    ends_on = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    currency = models.CharField(max_length=3, default='EUR')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pay_periods_created')
    closed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pay_periods_closed')
    closed_at = models.DateTimeField(blank=True, null=True)
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pay_periods_locked')
    locked_at = models.DateTimeField(blank=True, null=True)
    reopen_count = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = 'core'
        ordering = ['-starts_on', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['starts_on', 'ends_on'], name='pay_period_unique_range'),
            models.CheckConstraint(condition=models.Q(ends_on__gte=models.F('starts_on')), name='pay_period_valid_range'),
        ]
        indexes = [models.Index(fields=['status', 'starts_on', 'ends_on'], name='pay_period_status_idx')]


class WorkerTimesheet(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Offen'
        SUBMITTED = 'submitted', 'Eingereicht'
        APPROVED = 'approved', 'Freigegeben'
        REOPENED = 'reopened', 'Wieder geöffnet'
        LOCKED = 'locked', 'Gesperrt'

    pay_period = models.ForeignKey(PayPeriod, on_delete=models.CASCADE, related_name='timesheets')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='worker_timesheets')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    gross_minutes = models.PositiveIntegerField(default=0)
    paid_break_minutes = models.PositiveIntegerField(default=0)
    unpaid_break_minutes = models.PositiveIntegerField(default=0)
    net_minutes = models.PositiveIntegerField(default=0)
    gross_estimate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    entry_count = models.PositiveIntegerField(default=0)
    exception_count = models.PositiveIntegerField(default=0)
    blocking_exception_count = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='timesheets_approved')
    locked_at = models.DateTimeField(blank=True, null=True)
    review_note = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        app_label = 'core'
        ordering = ['worker__employee_number']
        constraints = [models.UniqueConstraint(fields=['pay_period', 'worker'], name='timesheet_period_worker_unique')]
        indexes = [models.Index(fields=['pay_period', 'status'], name='timesheet_period_status_idx')]


class TimesheetEntry(TimestampedModel):
    class ReviewStatus(models.TextChoices):
        PENDING = 'pending', 'Offen'
        APPROVED = 'approved', 'Freigegeben'
        REJECTED = 'rejected', 'Abgelehnt'

    timesheet = models.ForeignKey(WorkerTimesheet, on_delete=models.CASCADE, related_name='entries')
    time_entry = models.OneToOneField(TimeEntry, on_delete=models.PROTECT, related_name='timesheet_snapshot')
    clock_in = models.DateTimeField()
    clock_out = models.DateTimeField(blank=True, null=True)
    gross_minutes = models.PositiveIntegerField(default=0)
    paid_break_minutes = models.PositiveIntegerField(default=0)
    unpaid_break_minutes = models.PositiveIntegerField(default=0)
    net_minutes = models.PositiveIntegerField(default=0)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    amount_estimate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='timesheet_entries_reviewed')
    reviewed_at = models.DateTimeField(blank=True, null=True)
    review_note = models.TextField(blank=True)
    locked = models.BooleanField(default=False)

    class Meta:
        app_label = 'core'
        ordering = ['clock_in']
        indexes = [models.Index(fields=['timesheet', 'review_status'], name='timesheet_entry_review_idx')]


class TimesheetException(TimestampedModel):
    class Type(models.TextChoices):
        MISSING_ENTRY = 'missing_entry', 'Zeiteintrag fehlt'
        RUNNING_ENTRY = 'running_entry', 'Timer läuft'
        UNAPPROVED_ENTRY = 'unapproved_entry', 'Zeiteintrag nicht freigegeben'
        REJECTED_ENTRY = 'rejected_entry', 'Zeiteintrag abgelehnt'
        ATTENDANCE_NOTICE = 'attendance_notice', 'Attendance-Hinweis offen'

    class Severity(models.TextChoices):
        INFO = 'info', 'Hinweis'
        WARNING = 'warning', 'Warnung'
        BLOCKING = 'blocking', 'Blockierend'

    class Status(models.TextChoices):
        OPEN = 'open', 'Offen'
        RESOLVED = 'resolved', 'Erledigt'
        DISMISSED = 'dismissed', 'Verworfen'

    timesheet = models.ForeignKey(WorkerTimesheet, on_delete=models.CASCADE, related_name='exceptions')
    exception_type = models.CharField(max_length=30, choices=Type.choices)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.WARNING)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name='timesheet_exceptions')
    time_entry = models.ForeignKey(TimeEntry, on_delete=models.SET_NULL, null=True, blank=True, related_name='timesheet_exceptions')
    attendance_notice = models.ForeignKey('core.AttendanceNotice', on_delete=models.SET_NULL, null=True, blank=True, related_name='timesheet_exceptions')
    dedupe_key = models.CharField(max_length=220, unique=True)
    details = models.JSONField(default=dict, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='timesheet_exceptions_resolved')
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['-severity', '-created_at']
        indexes = [
            models.Index(fields=['timesheet', 'status', 'severity'], name='timesheet_exception_idx'),
            models.Index(fields=['exception_type', 'status'], name='timesheet_exception_type_idx'),
        ]

    def resolve(self, user=None, note='', dismissed=False):
        self.status = self.Status.DISMISSED if dismissed else self.Status.RESOLVED
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.resolution_note = note
        self.save(update_fields=['status', 'resolved_by', 'resolved_at', 'resolution_note', 'updated_at'])
