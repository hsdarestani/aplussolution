from django.db import models
from django.utils import timezone

from .models import Notification, TimestampedModel, User


class PushDevice(TimestampedModel):
    class Platform(models.TextChoices):
        ANDROID = 'android', 'Android'
        IOS = 'ios', 'iOS'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_devices')
    platform = models.CharField(max_length=20, choices=Platform.choices)
    token = models.TextField(unique=True)
    app_id = models.CharField(max_length=180, default='de.aplussolution.workforce')
    device_name = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    last_error = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'active'], name='core_push_u_active_idx'),
            models.Index(fields=['platform', 'active'], name='core_push_p_active_idx'),
        ]
        ordering = ['-last_seen_at']

    def __str__(self):
        return f'{self.user} · {self.platform} · {"aktiv" if self.active else "inaktiv"}'


class PushDelivery(TimestampedModel):
    """One delivery claim for one notification/device pair.

    Celery tasks can be retried or delivered more than once. The unique pair is
    the server-side guard that prevents the same native alert from being sent to
    the same registered device twice.
    """

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='push_deliveries')
    device = models.ForeignKey(PushDevice, on_delete=models.CASCADE, related_name='deliveries')
    sent_at = models.DateTimeField(blank=True, null=True)
    last_error = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['notification', 'device'], name='core_push_delivery_unique'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.notification_id} · {self.device_id}'


class NotificationPushRule(TimestampedModel):
    """Admin-editable native-push behavior for one notification family.

    The operational Notification row remains the source of truth for in-app
    history.  These rules only decide whether a native push is sent and how its
    title/body are rendered for Android/iOS.
    """

    key = models.CharField(max_length=80, unique=True)
    enabled = models.BooleanField(default=True)
    title_template = models.CharField(max_length=240, default='{title}', blank=True)
    body_template = models.TextField(default='{body}', blank=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.key