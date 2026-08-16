import hashlib
import secrets

from django.db import models
from django.utils import timezone

from .models import Location, Shift, TimeOffRequest, TimestampedModel, User, WorkerProfile
from .shift_slots import ShiftSlot


class SchedulingPolicy(TimestampedModel):
    name = models.CharField(max_length=120, default='Standard')
    active = models.BooleanField(default=True)
    min_hours_same_day = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    min_hours_between_days = models.DecimalField(max_digits=4, decimal_places=1, default=11)
    max_days_in_row = models.PositiveSmallIntegerField(default=6)
    max_days_per_week = models.PositiveSmallIntegerField(default=6)
    max_hours_per_day = models.DecimalField(max_digits=4, decimal_places=1, default=10)
    max_hours_per_week = models.DecimalField(max_digits=5, decimal_places=1, default=48)
    respect_worker_monthly_hours = models.BooleanField(default=True)
    allow_multiple_shifts_per_day = models.BooleanField(default=False)
    allow_overlapping_open_shifts = models.BooleanField(default=True)
    labor_sharing_enabled = models.BooleanField(default=True)
    task_lists_enabled = models.BooleanField(default=True)
    auto_schedule_enabled = models.BooleanField(default=True)
    pickup_approval_required = models.BooleanField(default=False)
    weekend_first = models.BooleanField(default=True)
    timezone_toggle_enabled = models.BooleanField(default=True)
    default_timezone = models.CharField(max_length=64, default='Europe/Berlin')

    class Meta:
        ordering = ['-active', 'name']


class ShiftTag(TimestampedModel):
    name = models.CharField(max_length=80, unique=True)
    color = models.CharField(max_length=20, default='#2457E6')
    active = models.BooleanField(default=True)


class ShiftTagLink(TimestampedModel):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='premium_tag_links')
    tag = models.ForeignKey(ShiftTag, on_delete=models.CASCADE, related_name='shift_links')

    class Meta:
        unique_together = ('shift', 'tag')


class ScheduleTemplate(TimestampedModel):
    name = models.CharField(max_length=160)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='schedule_templates')
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='schedule_templates_created')


class ScheduleTemplateShift(TimestampedModel):
    template = models.ForeignKey(ScheduleTemplate, on_delete=models.CASCADE, related_name='items')
    weekday = models.PositiveSmallIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_minutes = models.PositiveIntegerField(default=0)
    required_count = models.PositiveIntegerField(default=1)
    position = models.ForeignKey('core.Position', on_delete=models.PROTECT, related_name='premium_template_items')
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['weekday', 'start_time']


class TaskList(TimestampedModel):
    class Kind(models.TextChoices):
        TEAM = 'team', 'Team-Aufgaben'
        SHIFT = 'shift', 'Schicht-Aufgaben'

    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SHIFT)
    location = models.ForeignKey(Location, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_lists')
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_lists_created')


class TaskItem(TimestampedModel):
    task_list = models.ForeignKey(TaskList, on_delete=models.CASCADE, related_name='items')
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    required = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'created_at']


class TaskRun(TimestampedModel):
    task_list = models.ForeignKey(TaskList, on_delete=models.PROTECT, related_name='runs')
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, null=True, blank=True, related_name='task_runs')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='task_runs')
    run_date = models.DateField()
    assigned_worker = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_runs')
    closed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-run_date', 'created_at']


class TaskCompletion(TimestampedModel):
    run = models.ForeignKey(TaskRun, on_delete=models.CASCADE, related_name='completions')
    item = models.ForeignKey(TaskItem, on_delete=models.CASCADE, related_name='completions')
    completed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_completions')
    completed_at = models.DateTimeField(default=timezone.now)
    note = models.TextField(blank=True)

    class Meta:
        unique_together = ('run', 'item')


class ForecastMetric(TimestampedModel):
    name = models.CharField(max_length=120, unique=True)
    unit = models.CharField(max_length=40, default='Einheit')
    active = models.BooleanField(default=True)


class DailyForecast(TimestampedModel):
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='forecasts')
    date = models.DateField()
    metric = models.ForeignKey(ForecastMetric, on_delete=models.SET_NULL, null=True, blank=True, related_name='daily_values')
    projected_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    projected_units = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    labor_budget_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    labor_budget_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ('location', 'date', 'metric')
        ordering = ['date', 'location__name']


class StaffCallout(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = 'open', 'Offen'
        COVERED = 'covered', 'Abgedeckt'
        CLOSED = 'closed', 'Geschlossen'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='callouts')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='callouts')
    slot = models.ForeignKey(ShiftSlot, on_delete=models.SET_NULL, null=True, blank=True, related_name='callouts')
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    covered_by = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='covered_callouts')
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_callouts')
    resolved_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']


class TimeOffCategory(TimestampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.SlugField(max_length=50, unique=True)
    paid = models.BooleanField(default=False)
    requires_approval = models.BooleanField(default=True)
    active = models.BooleanField(default=True)


class TimeOffClassification(TimestampedModel):
    request = models.OneToOneField(TimeOffRequest, on_delete=models.CASCADE, related_name='classification')
    category = models.ForeignKey(TimeOffCategory, on_delete=models.PROTECT, related_name='requests')


class ReportDefinition(TimestampedModel):
    class Kind(models.TextChoices):
        SHIFTS = 'shifts', 'Schichten'
        TIMES = 'times', 'Zeiten'
        SHIFT_HISTORY = 'shift_history', 'Schichtverlauf'
        USERS = 'users', 'Mitarbeiter'
        TIME_OFF = 'time_off', 'Abwesenheiten'
        LABOR = 'labor', 'Personalkosten'

    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=30, choices=Kind.choices)
    columns = models.JSONField(default=list)
    filters = models.JSONField(default=dict, blank=True)
    sorting = models.JSONField(default=list, blank=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='report_definitions')
    shared = models.BooleanField(default=False)

    class Meta:
        ordering = ['name']


class PublicApiKey(TimestampedModel):
    name = models.CharField(max_length=120)
    prefix = models.CharField(max_length=16, unique=True)
    key_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    last_used_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='public_api_keys')

    @classmethod
    def issue(cls, *, name, scopes, created_by, expires_at=None):
        prefix = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        raw = f'aplus_{prefix}_{secret}'
        row = cls.objects.create(name=name, prefix=prefix, key_hash=hashlib.sha256(raw.encode('utf-8')).hexdigest(), scopes=scopes, created_by=created_by, expires_at=expires_at)
        return row, raw

    def accepts(self, raw):
        if not self.active or (self.expires_at and self.expires_at <= timezone.now()):
            return False
        return secrets.compare_digest(self.key_hash, hashlib.sha256(raw.encode('utf-8')).hexdigest())


class WebhookSubscription(TimestampedModel):
    name = models.CharField(max_length=120)
    endpoint_url = models.URLField(max_length=500)
    signing_secret = models.CharField(max_length=128)
    events = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='webhook_subscriptions')


class WebhookDelivery(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Ausstehend'
        DELIVERED = 'delivered', 'Zugestellt'
        FAILED = 'failed', 'Fehlgeschlagen'

    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.CASCADE, related_name='deliveries')
    event_type = models.CharField(max_length=120)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveIntegerField(default=0)
    response_status = models.PositiveIntegerField(blank=True, null=True)
    response_body = models.TextField(blank=True)
    next_attempt_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']


class SamlIdentity(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saml_identities')
    idp_entity_id = models.CharField(max_length=500)
    name_id = models.CharField(max_length=500)

    class Meta:
        unique_together = ('idp_entity_id', 'name_id')


class ExternalIntegration(TimestampedModel):
    class Kind(models.TextChoices):
        PAYROLL = 'payroll', 'Payroll'
        POS = 'pos', 'POS'
        GENERIC = 'generic', 'Generisch'

    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    provider = models.CharField(max_length=80)
    endpoint_url = models.URLField(max_length=500, blank=True)
    credential_env = models.JSONField(default=dict, blank=True)
    config = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
    last_sync_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='external_integrations')
