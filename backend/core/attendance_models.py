from django.db import models

from .models import TimeEntry, TimestampedModel, User, WorkerProfile


class TimeEntryCorrection(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Offen'
        APPROVED = 'approved', 'Genehmigt'
        REJECTED = 'rejected', 'Abgelehnt'
        CANCELLED = 'cancelled', 'Zurückgezogen'

    entry = models.ForeignKey(TimeEntry, on_delete=models.CASCADE, related_name='correction_requests')
    requested_by = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='time_correction_requests')
    requested_clock_in = models.DateTimeField(blank=True, null=True)
    requested_clock_out = models.DateTimeField(blank=True, null=True)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_time_corrections')
    decided_at = models.DateTimeField(blank=True, null=True)
    decision_note = models.TextField(blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['-created_at']
