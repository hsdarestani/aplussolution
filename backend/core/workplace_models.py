from decimal import Decimal

from django.conf import settings
from django.db import models

from .models import Location, TimestampedModel, User, WorkerProfile
from .scheduling_models import ScheduleGroup


class WorkplaceSettings(TimestampedModel):
    class TimeFormat(models.TextChoices):
        H24 = '24h', '24 Stunden'
        H12 = '12h', '12 Stunden'

    class OvertimeMode(models.TextChoices):
        OFF = 'off', 'Aus'
        WARN = 'warn', 'Warnen'
        BLOCK = 'block', 'Blockieren'

    company_name = models.CharField(max_length=180, default='A+ Solution GmbH')
    timezone = models.CharField(max_length=64, default='Europe/Berlin')
    week_starts_on = models.PositiveSmallIntegerField(default=0, help_text='0=Montag, 6=Sonntag')
    time_format = models.CharField(max_length=8, choices=TimeFormat.choices, default=TimeFormat.H24)
    currency = models.CharField(max_length=3, default='EUR')
    overtime_daily_hours = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('8.00'))
    overtime_weekly_hours = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('40.00'))
    overtime_mode = models.CharField(max_length=10, choices=OvertimeMode.choices, default=OvertimeMode.WARN)
    overtime_multiplier = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('1.25'))
    labor_sharing_enabled = models.BooleanField(default=True)
    manager_can_manage_roles = models.BooleanField(default=False)

    class Meta:
        app_label = 'core'
        verbose_name_plural = 'Workplace settings'

    @classmethod
    def load(cls):
        obj = cls.objects.order_by('created_at').first()
        return obj or cls.objects.create()

    @property
    def allow_overlapping_open_shifts(self):
        from .scheduler_completion_models import SchedulerCompletionSettings
        return SchedulerCompletionSettings.load().allow_overlapping_open_shifts

    @property
    def require_shift_confirmation(self):
        from .scheduler_completion_models import SchedulerCompletionSettings
        return SchedulerCompletionSettings.load().require_shift_confirmation


class AccessRole(TimestampedModel):
    class WageVisibility(models.TextChoices):
        NONE = 'none', 'Keine'
        SCOPED = 'scoped', 'Nur eigener Bereich'
        ALL = 'all', 'Alle'

    code = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=list, blank=True)
    wage_visibility = models.CharField(max_length=10, choices=WageVisibility.choices, default=WageVisibility.NONE)
    is_system = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = 'core'
        ordering = ['name']

    def __str__(self):
        return self.name


class UserAccessAssignment(TimestampedModel):
    class ScopeMode(models.TextChoices):
        ALL = 'all', 'Gesamter Betrieb'
        SCOPED = 'scoped', 'Zugeordnete Bereiche'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='access_assignment')
    access_role = models.ForeignKey(AccessRole, on_delete=models.PROTECT, related_name='assignments')
    scope_mode = models.CharField(max_length=10, choices=ScopeMode.choices, default=ScopeMode.SCOPED)
    schedule_groups = models.ManyToManyField(ScheduleGroup, related_name='access_assignments', blank=True)
    locations = models.ManyToManyField(Location, related_name='access_assignments', blank=True)
    workers = models.ManyToManyField(WorkerProfile, related_name='supervisor_assignments', blank=True)
    can_share_labor = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = 'core'
        ordering = ['user__first_name', 'user__last_name', 'user__email']

    def __str__(self):
        return f'{self.user} – {self.access_role}'
