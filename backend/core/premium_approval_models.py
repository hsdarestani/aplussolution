from django.db import models

from .models import Location, Shift, TimestampedModel, User, WorkerProfile


class ShiftPickupRequest(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Offen'
        APPROVED = 'approved', 'Genehmigt'
        REJECTED = 'rejected', 'Abgelehnt'
        CANCELLED = 'cancelled', 'Storniert'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='pickup_requests')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='pickup_requests')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pickup_requests_decided')
    decision_note = models.TextField(blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['shift', 'worker'], condition=models.Q(status='pending'), name='unique_pending_shift_pickup')
        ]


class WorkerLocationMembership(TimestampedModel):
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='location_memberships')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='worker_memberships')
    home = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = 'core'
        unique_together = ('worker', 'location')
        ordering = ['worker__employee_number', '-home', 'location__name']
