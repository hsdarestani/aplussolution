from django.db import models
from django.utils import timezone

from .models import TimestampedModel, User
from .payroll_models import PayPeriod


class IntegrationApiKey(TimestampedModel):
    name = models.CharField(max_length=160)
    prefix = models.CharField(max_length=20, unique=True, db_index=True)
    secret_hash = models.CharField(max_length=255)
    scopes = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='integration_api_keys_created')
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    revoked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def usable(self):
        return self.active and not self.revoked_at and (not self.expires_at or self.expires_at > timezone.now())


class WebhookSubscription(TimestampedModel):
    name = models.CharField(max_length=160)
    url = models.URLField(max_length=500)
    secret_encrypted = models.TextField()
    event_types = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True)
    timeout_seconds = models.PositiveSmallIntegerField(default=10)
    max_attempts = models.PositiveSmallIntegerField(default=6)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='webhook_subscriptions_created')
    last_success_at = models.DateTimeField(blank=True, null=True)
    last_failure_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['name']


class WebhookDelivery(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ausstehend'
        RETRY = 'retry', 'Wiederholung'
        DELIVERED = 'delivered', 'Zugestellt'
        DEAD = 'dead', 'Dead Letter'

    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.CASCADE, related_name='deliveries')
    event_id = models.UUIDField()
    event_type = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_http_status = models.PositiveSmallIntegerField(blank=True, null=True)
    last_error = models.TextField(blank=True)
    delivered_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['subscription', 'event_id'], name='webhook_delivery_unique_event')]
        indexes = [models.Index(fields=['status', 'next_attempt_at'], name='webhook_delivery_due_idx')]


class SamlIdentityProvider(TimestampedModel):
    name = models.CharField(max_length=160, default='Company SSO')
    enabled = models.BooleanField(default=False)
    sp_entity_id = models.CharField(max_length=300, blank=True)
    idp_entity_id = models.CharField(max_length=300)
    sso_url = models.URLField(max_length=500)
    x509_certificate = models.TextField()
    allowed_domains = models.JSONField(default=list, blank=True)
    auto_provision = models.BooleanField(default=False)
    default_role = models.CharField(max_length=20, choices=User.Role.choices, default=User.Role.WORKER)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='saml_settings_updated')

    class Meta:
        ordering = ['name']


class PayrollConnector(TimestampedModel):
    class Provider(models.TextChoices):
        DATEV_CSV = 'datev_csv', 'DATEV CSV'
        GENERIC_JSON = 'generic_json', 'Generic JSON API'

    name = models.CharField(max_length=160)
    provider = models.CharField(max_length=30, choices=Provider.choices)
    configuration = models.JSONField(default=dict, blank=True)
    credentials_encrypted = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='payroll_connectors_created')
    last_export_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['name']


class PayrollExportRun(TimestampedModel):
    class Status(models.TextChoices):
        RUNNING = 'running', 'Läuft'
        SUCCESS = 'success', 'Erfolgreich'
        FAILED = 'failed', 'Fehlgeschlagen'

    connector = models.ForeignKey(PayrollConnector, on_delete=models.PROTECT, related_name='exports')
    pay_period = models.ForeignKey(PayPeriod, on_delete=models.PROTECT, related_name='integration_exports')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    record_count = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='payroll_exports_created')
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['connector', 'pay_period'], name='payroll_connector_period_unique')]
