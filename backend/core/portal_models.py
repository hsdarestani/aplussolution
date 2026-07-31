from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import TimestampedModel, User


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


@receiver(post_save, sender=User)
def keep_synced_workers_unactivated_until_credentials_exist(sender, instance, **kwargs):
    if (
        instance.role == User.Role.WORKER
        and instance.wiw_id
        and instance.is_onboarded
        and not instance.has_usable_password()
    ):
        User.objects.filter(pk=instance.pk).update(is_onboarded=False)
