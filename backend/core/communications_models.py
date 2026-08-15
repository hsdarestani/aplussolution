from django.db import models
from django.utils import timezone

from .models import Conversation, Message, Notification, TimestampedModel, User


class CommunicationSettings(TimestampedModel):
    workchat_enabled = models.BooleanField(default=True)
    employees_can_post_workplace = models.BooleanField(default=False)
    users_can_create_channels = models.BooleanField(default=False)
    images_enabled = models.BooleanField(default=True)
    sms_fallback_enabled = models.BooleanField(default=False)

    @classmethod
    def load(cls):
        obj = cls.objects.order_by('created_at').first()
        if obj:
            return obj
        return cls.objects.create()


class NotificationPreference(TimestampedModel):
    class Category(models.TextChoices):
        TIME_OFF = 'time_off', 'Abwesenheitsanträge'
        SWAP_DROP = 'swap_drop', 'Tausch / Abgabe'
        OPEN_SHIFT = 'open_shift', 'Offene Schichten'
        ABSENCE = 'absence', 'Abwesenheiten'
        SCHEDULE = 'schedule_update', 'Dienstplanänderungen'
        NEW_USER = 'new_user', 'Neue Benutzer'
        AVAILABILITY = 'availability', 'Verfügbarkeitsänderungen'
        CLOCK = 'clock_reminder', 'Ein-/Ausstempel-Erinnerungen'
        OVERTIME = 'overtime', 'Überstunden'
        PAYROLL = 'payroll', 'Abrechnung'
        REPORTS = 'reports', 'Berichte'
        WORKPLACE = 'workplace', 'Betriebsmitteilungen'
        SHIFT_REMINDER = 'shift_reminder', 'Schichterinnerungen'
        WORKCHAT = 'workchat', 'WorkChat'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notification_preferences')
    category = models.CharField(max_length=40, choices=Category.choices)
    in_app_enabled = models.BooleanField(default=True)
    push_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)
    reminder_minutes = models.PositiveIntegerField(default=1440)
    dnd_start = models.TimeField(blank=True, null=True)
    dnd_end = models.TimeField(blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'category'], name='uniq_notification_pref_user_category')]
        ordering = ['category']


class NotificationState(TimestampedModel):
    class Priority(models.TextChoices):
        LOW = 'low', 'Niedrig'
        NORMAL = 'normal', 'Normal'
        HIGH = 'high', 'Hoch'
        URGENT = 'urgent', 'Dringend'

    notification = models.OneToOneField(Notification, on_delete=models.CASCADE, related_name='delivery_state')
    category = models.CharField(max_length=40, choices=NotificationPreference.Category.choices, default=NotificationPreference.Category.WORKPLACE)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.NORMAL)
    read_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    data = models.JSONField(default=dict, blank=True)
    dedupe_key = models.CharField(max_length=180, blank=True, db_index=True)
    delivery_enqueued_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['category', 'read_at'], name='notif_state_category_read_idx'),
            models.Index(fields=['deleted_at', 'created_at'], name='notif_state_del_created_idx'),
        ]


class DeviceRegistration(TimestampedModel):
    class Platform(models.TextChoices):
        IOS = 'ios', 'iOS'
        ANDROID = 'android', 'Android'
        WEB = 'web', 'Web'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_devices')
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=16, choices=Platform.choices)
    device_name = models.CharField(max_length=160, blank=True)
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    app_version = models.CharField(max_length=40, blank=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'active'], name='device_user_active_idx')]


class NotificationDelivery(TimestampedModel):
    class Channel(models.TextChoices):
        PUSH = 'push', 'Push'
        EMAIL = 'email', 'E-Mail'
        SMS = 'sms', 'SMS'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ausstehend'
        SENT = 'sent', 'Gesendet'
        SKIPPED = 'skipped', 'Übersprungen'
        FAILED = 'failed', 'Fehlgeschlagen'

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name='delivery_attempts')
    channel = models.CharField(max_length=12, choices=Channel.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=40, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    sent_at = models.DateTimeField(blank=True, null=True)
    error = models.TextField(blank=True)
    provider_response = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['notification', 'channel'], name='uniq_notification_delivery_channel')]


class ConversationChannel(TimestampedModel):
    class ChannelType(models.TextChoices):
        WORKPLACE = 'workplace', 'Betrieb'
        GROUP = 'group', 'Gruppe'
        DIRECT = 'direct', 'Direkt'

    conversation = models.OneToOneField(Conversation, on_delete=models.CASCADE, related_name='channel')
    channel_type = models.CharField(max_length=16, choices=ChannelType.choices, default=ChannelType.GROUP)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_workchat_channels')
    active = models.BooleanField(default=True)
    pinned = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=['channel_type', 'active'], name='chat_channel_type_active_idx')]


class ConversationMembership(TimestampedModel):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        MODERATOR = 'moderator', 'Moderator'
        MEMBER = 'member', 'Mitglied'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='channel_memberships')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='channel_memberships')
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MEMBER)
    notifications_enabled = models.BooleanField(default=True)
    muted = models.BooleanField(default=False)
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(blank=True, null=True)
    last_read_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['conversation', 'user'], name='uniq_chat_membership_user')]
        indexes = [models.Index(fields=['user', 'left_at'], name='chat_member_user_left_idx')]


class MessageState(TimestampedModel):
    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name='message_state')
    edited_at = models.DateTimeField(blank=True, null=True)
    deleted_at = models.DateTimeField(blank=True, null=True)
    deleted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='deleted_chat_messages')
