import hashlib
import secrets
import uuid

from django.db import models
from django.utils import timezone

from .models import Location, Shift, TimeEntry, TimestampedModel, User, WorkerProfile


class AttendancePolicy(TimestampedModel):
    class Enforcement(models.TextChoices):
        OFF = 'off', 'Aus'
        WARN = 'warn', 'Hinweis'
        BLOCK = 'block', 'Blockieren'

    name = models.CharField(max_length=120, default='Standard')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='attendance_policies', blank=True, null=True)
    active = models.BooleanField(default=True)
    priority = models.IntegerField(default=0)

    early_clock_in_minutes = models.PositiveIntegerField(default=15)
    early_clock_in_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.OFF)
    late_clock_in_grace_minutes = models.PositiveIntegerField(default=5)
    early_clock_out_grace_minutes = models.PositiveIntegerField(default=5)
    late_clock_out_grace_minutes = models.PositiveIntegerField(default=15)
    no_show_after_minutes = models.PositiveIntegerField(default=30)
    missed_clock_out_after_minutes = models.PositiveIntegerField(default=120)

    clock_in_location_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.BLOCK)
    clock_out_location_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.BLOCK)
    allow_unscheduled_clock_in = models.BooleanField(default=False)

    required_break_after_minutes = models.PositiveIntegerField(default=360)
    required_break_minutes = models.PositiveIntegerField(default=30)
    default_break_paid = models.BooleanField(default=False)
    auto_deduct_unpaid_breaks = models.BooleanField(default=False)
    break_attestation_required = models.BooleanField(default=False)
    end_of_shift_attestation_required = models.BooleanField(default=False)

    terminal_photo_clock_in = models.BooleanField(default=False)
    terminal_photo_clock_out = models.BooleanField(default=False)

    class Meta:
        app_label = 'core'
        ordering = ['-priority', '-updated_at']
        indexes = [models.Index(fields=['active', 'location', 'priority'], name='att_policy_scope_idx')]


class AttendanceBreak(TimestampedModel):
    class Status(models.TextChoices):
        PLANNED = 'planned', 'Geplant'
        RUNNING = 'running', 'Läuft'
        COMPLETED = 'completed', 'Beendet'
        CANCELLED = 'cancelled', 'Storniert'

    class Source(models.TextChoices):
        SCHEDULED = 'scheduled', 'Dienstplan'
        MANUAL = 'manual', 'Mitarbeiter'
        AUTO_DEDUCT = 'auto_deduct', 'Automatischer Abzug'
        TERMINAL = 'terminal', 'Terminal'
        MANAGER = 'manager', 'Administration'

    entry = models.ForeignKey(TimeEntry, on_delete=models.CASCADE, related_name='attendance_breaks')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    paid = models.BooleanField(default=False)
    scheduled_minutes = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    deducted_minutes = models.PositiveIntegerField(default=0)
    started_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='attendance_breaks_started', blank=True, null=True)
    ended_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='attendance_breaks_ended', blank=True, null=True)
    note = models.CharField(max_length=250, blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['created_at']
        indexes = [models.Index(fields=['entry', 'status'], name='att_break_entry_idx')]

    @property
    def actual_minutes(self):
        if self.started_at:
            end = self.ended_at or timezone.now()
            return max(0, int((end - self.started_at).total_seconds() // 60))
        return int(self.deducted_minutes or 0)

    @property
    def deductible_minutes(self):
        if self.paid or self.status == self.Status.CANCELLED:
            return 0
        if self.source == self.Source.AUTO_DEDUCT:
            return int(self.deducted_minutes or 0)
        return self.actual_minutes if self.status == self.Status.COMPLETED else 0


class AttendanceClockEvent(TimestampedModel):
    class Kind(models.TextChoices):
        CLOCK_IN = 'clock_in', 'Einstempeln'
        CLOCK_OUT = 'clock_out', 'Ausstempeln'
        BREAK_START = 'break_start', 'Pausenbeginn'
        BREAK_END = 'break_end', 'Pausenende'

    class Method(models.TextChoices):
        WEB = 'web', 'Web'
        MOBILE = 'mobile', 'Mobil'
        TERMINAL = 'terminal', 'Terminal'
        MANAGER = 'manager', 'Administration'
        API = 'api', 'API'

    entry = models.ForeignKey(TimeEntry, on_delete=models.CASCADE, related_name='clock_events')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.WEB)
    occurred_at = models.DateTimeField(default=timezone.now)
    lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    note = models.CharField(max_length=250, blank=True)
    photo = models.ImageField(upload_to='attendance/%Y/%m/', blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['occurred_at']
        indexes = [models.Index(fields=['entry', 'kind', 'occurred_at'], name='att_clock_event_idx')]


class AttendanceNotice(TimestampedModel):
    class Type(models.TextChoices):
        EARLY_CLOCK_IN = 'early_clock_in', 'Zu früh eingestempelt'
        LATE_CLOCK_IN = 'late_clock_in', 'Zu spät eingestempelt'
        EARLY_CLOCK_OUT = 'early_clock_out', 'Zu früh ausgestempelt'
        LATE_CLOCK_OUT = 'late_clock_out', 'Zu spät ausgestempelt'
        WRONG_LOCATION = 'wrong_location', 'Falscher Standort'
        MISSED_CLOCK_IN = 'missed_clock_in', 'Einstempeln fehlt'
        MISSED_CLOCK_OUT = 'missed_clock_out', 'Ausstempeln fehlt'
        NO_SHOW = 'no_show', 'Nicht erschienen'
        NOT_SCHEDULED = 'not_scheduled', 'Nicht eingeplant'
        PHOTO_MISSING = 'photo_missing', 'Foto fehlt'
        BREAK_MISSED = 'break_missed', 'Pause fehlt'
        BREAK_SHORT = 'break_short', 'Pause zu kurz'
        ATTESTATION_MISSING = 'attestation_missing', 'Bestätigung fehlt'
        TERMINAL_DENIED = 'terminal_denied', 'Terminal-Zugriff abgelehnt'

    class Severity(models.TextChoices):
        INFO = 'info', 'Hinweis'
        WARNING = 'warning', 'Warnung'
        CRITICAL = 'critical', 'Kritisch'

    class Status(models.TextChoices):
        OPEN = 'open', 'Offen'
        ACKNOWLEDGED = 'acknowledged', 'Gesehen'
        RESOLVED = 'resolved', 'Erledigt'
        DISMISSED = 'dismissed', 'Verworfen'

    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='attendance_notices')
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='attendance_notices', blank=True, null=True)
    entry = models.ForeignKey(TimeEntry, on_delete=models.CASCADE, related_name='attendance_notices', blank=True, null=True)
    break_record = models.ForeignKey(AttendanceBreak, on_delete=models.SET_NULL, related_name='notices', blank=True, null=True)
    notice_type = models.CharField(max_length=30, choices=Type.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    detected_at = models.DateTimeField(default=timezone.now)
    value_minutes = models.IntegerField(blank=True, null=True)
    details = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=180, unique=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='resolved_attendance_notices', blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    resolution_note = models.CharField(max_length=250, blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['status', 'severity', 'detected_at'], name='att_notice_status_idx'),
            models.Index(fields=['worker', 'notice_type'], name='att_notice_worker_idx'),
        ]


class AttendanceAttestation(TimestampedModel):
    class Kind(models.TextChoices):
        BREAK = 'break', 'Pausenbestätigung'
        END_OF_SHIFT = 'end_of_shift', 'Schichtende'

    class Source(models.TextChoices):
        SELF_SERVICE = 'self_service', 'Mitarbeiterportal'
        TERMINAL = 'terminal', 'Terminal'
        MANAGER = 'manager', 'Administration'

    entry = models.ForeignKey(TimeEntry, on_delete=models.CASCADE, related_name='attestations')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='attendance_attestations')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    answers = models.JSONField(default=dict)
    note = models.TextField(blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.SELF_SERVICE)
    submitted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        app_label = 'core'
        ordering = ['-submitted_at']
        constraints = [models.UniqueConstraint(fields=['entry', 'kind'], name='att_attestation_unique')]


class AttendanceTerminal(TimestampedModel):
    name = models.CharField(max_length=120)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='attendance_terminals')
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token_hash = models.CharField(max_length=64)
    active = models.BooleanField(default=True)
    photo_clock_in = models.BooleanField(default=False)
    photo_clock_out = models.BooleanField(default=False)
    last_seen_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='attendance_terminals_created', blank=True, null=True)

    class Meta:
        app_label = 'core'
        ordering = ['location__name', 'name']
        indexes = [models.Index(fields=['active', 'location'], name='att_terminal_scope_idx')]

    @staticmethod
    def hash_token(token):
        return hashlib.sha256(str(token).encode('utf-8')).hexdigest()

    @classmethod
    def issue_token(cls):
        return secrets.token_urlsafe(32)

    def token_matches(self, token):
        if not token or not self.token_hash:
            return False
        return secrets.compare_digest(self.token_hash, self.hash_token(token))
