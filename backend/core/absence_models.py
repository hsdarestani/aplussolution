from django.db import models
from django.utils import timezone

from .models import Shift, TimeOffRequest, TimestampedModel, User, WorkerProfile


class ShiftAbsenceCase(TimestampedModel):
    """One operational absence/callout and its replacement lifecycle."""

    class Kind(models.TextChoices):
        SICK = 'sick', 'Krank'
        EMERGENCY = 'emergency', 'Notfall'
        PERSONAL = 'personal', 'Persönlich verhindert'
        NO_SHOW = 'no_show', 'Nicht erschienen'
        APPROVED_TIME_OFF = 'approved_time_off', 'Genehmigte Abwesenheit'
        OTHER = 'other', 'Sonstiger Ausfall'

    class Source(models.TextChoices):
        WORKER = 'worker', 'Mitarbeiter'
        MANAGER = 'manager', 'Disposition'
        TIME_OFF = 'time_off', 'Abwesenheitsantrag'
        ATTENDANCE = 'attendance', 'Zeiterfassung'
        SYSTEM = 'system', 'System'

    class Status(models.TextChoices):
        REPORTED = 'reported', 'Gemeldet'
        COVERAGE_PENDING = 'coverage_pending', 'Ersatz offen'
        OFFERED = 'offered', 'Angebote versendet'
        MOVED_TO_OPEN = 'moved_to_open', 'Als OpenShift veröffentlicht'
        COVERED = 'covered', 'Ersatz gefunden'
        RESOLVED_UNCOVERED = 'resolved_uncovered', 'Ohne Ersatz abgeschlossen'
        CANCELLED = 'cancelled', 'Storniert'

    class CoverageStrategy(models.TextChoices):
        NONE = 'none', 'Noch nicht gewählt'
        OPEN_SHIFT = 'open_shift', 'OpenShift'
        TARGETED = 'targeted', 'Gezielte Ersatzanfrage'
        DIRECT = 'direct', 'Direkte Ersatzbesetzung'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='absence_cases')
    slot = models.ForeignKey('core.ShiftSlot', on_delete=models.SET_NULL, related_name='absence_cases', blank=True, null=True)
    absent_worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='absence_cases')
    time_off_request = models.ForeignKey(TimeOffRequest, on_delete=models.SET_NULL, related_name='absence_cases', blank=True, null=True)
    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.OTHER)
    source = models.CharField(max_length=30, choices=Source.choices, default=Source.WORKER)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.REPORTED)
    coverage_strategy = models.CharField(max_length=30, choices=CoverageStrategy.choices, default=CoverageStrategy.NONE)
    reason_note = models.TextField(blank=True)
    manager_note = models.TextField(blank=True)
    short_notice = models.BooleanField(default=False)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='reported_absence_cases', blank=True, null=True)
    reported_at = models.DateTimeField(default=timezone.now)
    replacement_worker = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, related_name='replacement_cases', blank=True, null=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='resolved_absence_cases', blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        app_label = 'core'
        ordering = ['-reported_at']
        indexes = [
            models.Index(fields=['status', 'reported_at']),
            models.Index(fields=['shift', 'absent_worker']),
            models.Index(fields=['short_notice', 'status']),
        ]

    @property
    def is_active(self):
        return self.status in {
            self.Status.REPORTED,
            self.Status.COVERAGE_PENDING,
            self.Status.OFFERED,
            self.Status.MOVED_TO_OPEN,
        }


class CoverageOffer(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Offen'
        ACCEPTED = 'accepted', 'Angenommen'
        DECLINED = 'declined', 'Abgelehnt'
        CANCELLED = 'cancelled', 'Storniert'
        EXPIRED = 'expired', 'Abgelaufen'

    case = models.ForeignKey(ShiftAbsenceCase, on_delete=models.CASCADE, related_name='offers')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='coverage_offers')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    offered_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='coverage_offers_sent', blank=True, null=True)
    offered_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(blank=True, null=True)
    responded_at = models.DateTimeField(blank=True, null=True)
    eligibility_snapshot = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=250, blank=True)

    class Meta:
        app_label = 'core'
        unique_together = ('case', 'worker')
        ordering = ['-offered_at']
        indexes = [models.Index(fields=['worker', 'status', 'expires_at'])]
