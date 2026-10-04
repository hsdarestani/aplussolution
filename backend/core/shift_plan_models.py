import uuid

from django.conf import settings
from django.db import models


class ShiftPlanDocument(models.Model):
    """One uploaded event plan PDF.

    A single event plan can cover several service shifts or event days. The PDF
    is therefore stored once and linked to one or more Shift rows through
    ShiftPlanAttachment.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to='shift_plans/%Y/%m/')
    original_name = models.CharField(max_length=255)
    checksum = models.CharField(max_length=64, unique=True, db_index=True)
    extracted_event_numbers = models.JSONField(default=list, blank=True)
    extracted_event_dates = models.JSONField(default=list, blank=True)
    extracted_service_windows = models.JSONField(default=dict, blank=True)
    extracted_preview = models.TextField(blank=True)
    client = models.ForeignKey(
        'ClientCompany',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='shift_plan_documents',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='uploaded_shift_plan_documents',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.original_name


class ShiftPlanAttachment(models.Model):
    class Visibility(models.TextChoices):
        ALL = 'all', 'Alle Mitarbeiter'
        WORKER = 'worker', 'Ein Mitarbeiter'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shift = models.ForeignKey('Shift', on_delete=models.CASCADE, related_name='plan_attachments')
    visibility = models.CharField(max_length=20, choices=Visibility.choices, default=Visibility.ALL)
    target_worker = models.ForeignKey(
        'WorkerProfile',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='targeted_shift_plan_attachments',
    )
    document = models.ForeignKey(ShiftPlanDocument, on_delete=models.CASCADE, related_name='attachments')
    match_score = models.PositiveSmallIntegerField(default=0)
    match_reason = models.CharField(max_length=500, blank=True)
    matched_automatically = models.BooleanField(default=False)
    attached_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attached_shift_plans',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['shift', 'document'], name='unique_shift_plan_document'),
        ]

    def __str__(self):
        return f'{self.shift_id}: {self.document.original_name}'
