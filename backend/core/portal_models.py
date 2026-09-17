from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ClientCompany, Location, Shift, TimestampedModel, User


class PortalInvitation(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portal_invitations')
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_portal_invitations')
    delivered_at = models.DateTimeField(blank=True, null=True)
    delivery_channel = models.CharField(max_length=30, blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'used_at', 'expires_at'])]


class ClientPortalAccess(TimestampedModel):
    """One explicit portal identity mapped to exactly one customer account."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_portal_access')
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name='portal_accesses')
    label = models.CharField(max_length=200, blank=True)
    read_only = models.BooleanField(default=False)
    location_scope = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='portal_accesses',
    )
    capabilities = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['client__name', 'user__first_name', 'user__last_name']
        indexes = [models.Index(fields=['client', 'read_only'], name='client_access_scope_idx')]

    def __str__(self):
        return self.label or self.user.get_full_name() or self.user.email


class ClientShiftChangeRequest(TimestampedModel):
    class RequestType(models.TextChoices):
        CHANGE = 'change', 'Zeit / Datum ändern'
        CANCEL = 'cancel', 'Schicht stornieren'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Offen'
        APPROVED = 'approved', 'Genehmigt'
        REJECTED = 'rejected', 'Abgelehnt'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='client_change_requests')
    client = models.ForeignKey(ClientCompany, on_delete=models.CASCADE, related_name='shift_change_requests')
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='client_shift_change_requests')
    request_type = models.CharField(max_length=20, choices=RequestType.choices)
    requested_starts_at = models.DateTimeField(blank=True, null=True)
    requested_ends_at = models.DateTimeField(blank=True, null=True)
    note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    original_snapshot = models.JSONField(default=dict, blank=True)
    decision_snapshot = models.JSONField(default=dict, blank=True)
    decided_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decided_client_shift_change_requests',
    )
    decided_at = models.DateTimeField(blank=True, null=True)
    admin_note = models.TextField(blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='client_req_status_idx'),
            models.Index(fields=['shift', 'status'], name='client_req_shift_idx'),
        ]


@receiver(post_save, sender=User)
def keep_synced_workers_unactivated_until_credentials_exist(sender, instance, **kwargs):
    if (
        instance.role == User.Role.WORKER
        and instance.wiw_id
        and instance.is_onboarded
        and not instance.has_usable_password()
    ):
        User.objects.filter(pk=instance.pk).update(is_onboarded=False)
