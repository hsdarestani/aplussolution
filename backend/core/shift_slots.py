from django.db import models

from .models import Shift, TimestampedModel, WorkerProfile


class ShiftSlot(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Offen'
        CLAIMED = 'claimed', 'Übernommen'
        CANCELLED = 'cancelled', 'Storniert'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='slots')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, related_name='shift_slots', blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    source = models.CharField(max_length=30, default='system')
    wiw_shift_id = models.CharField(max_length=80, unique=True, blank=True, null=True)
    claimed_at = models.DateTimeField(blank=True, null=True)
    released_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        app_label = 'core'
        ordering = ['shift__starts_at', 'created_at']
