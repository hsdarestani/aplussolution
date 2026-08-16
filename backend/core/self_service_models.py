from decimal import Decimal

from django.conf import settings
from django.db import models

from .models import Shift, TimeOffRequest, TimestampedModel, User, WorkerProfile


class SelfServiceSettings(TimestampedModel):
    class TeamScheduleVisibility(models.TextChoices):
        NONE = 'none', 'Nur eigene Schichten'
        POSITIONS = 'positions', 'Gemeinsame Positionen'
        ALL = 'all', 'Gesamter Team-Dienstplan'

    availability_enabled = models.BooleanField(default=True)
    show_availability_to_all = models.BooleanField(default=False)
    availability_notice_days = models.PositiveSmallIntegerField(default=0)
    team_schedule_visibility = models.CharField(
        max_length=20,
        choices=TeamScheduleVisibility.choices,
        default=TeamScheduleVisibility.NONE,
    )
    global_user_privacy = models.BooleanField(default=False)
    allow_shift_release = models.BooleanField(default=True)
    release_cutoff_hours = models.PositiveSmallIntegerField(default=0)
    allow_shift_drop = models.BooleanField(default=True)
    drop_cutoff_hours = models.PositiveSmallIntegerField(default=0)
    allow_shift_swap = models.BooleanField(default=True)
    swap_cutoff_hours = models.PositiveSmallIntegerField(default=0)
    require_manager_review_swaps_drops = models.BooleanField(default=True)
    time_off_enabled = models.BooleanField(default=True)
    time_off_notice_days = models.PositiveSmallIntegerField(default=0)
    time_off_max_paid_hours_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('8.00'))

    class Meta:
        app_label = 'core'
        verbose_name_plural = 'Self-service settings'

    @classmethod
    def load(cls):
        obj = cls.objects.order_by('created_at').first()
        return obj or cls.objects.create()


class UserSelfServicePreference(TimestampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='self_service_preference')
    hide_contact_info = models.BooleanField(default=True)
    preferred_weekly_hours = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)

    class Meta:
        app_label = 'core'


class AvailabilityPreferenceSeries(TimestampedModel):
    class Kind(models.TextChoices):
        PREFERRED = 'preferred', 'Bevorzugt'
        UNAVAILABLE = 'unavailable', 'Nicht verfügbar'

    class Recurrence(models.TextChoices):
        ONCE = 'once', 'Einmalig'
        DAILY = 'daily', 'Täglich'
        WEEKLY = 'weekly', 'Wöchentlich'
        TWO_WEEKS = 'two_weeks', 'Alle 2 Wochen'

    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='availability_preference_series')
    kind = models.CharField(max_length=20, choices=Kind.choices)
    starts_on = models.DateField()
    ends_on = models.DateField()
    all_day = models.BooleanField(default=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    recurrence = models.CharField(max_length=20, choices=Recurrence.choices, default=Recurrence.ONCE)
    weekdays = models.JSONField(default=list, blank=True)
    note = models.CharField(max_length=250, blank=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='availability_series_created')

    class Meta:
        app_label = 'core'
        ordering = ['starts_on', 'worker__employee_number']
        indexes = [models.Index(fields=['worker', 'active', 'starts_on', 'ends_on'], name='avail_series_range_idx')]


class TimeOffType(TimestampedModel):
    class Kind(models.TextChoices):
        HOLIDAY = 'holiday', 'Urlaub'
        PERSONAL = 'personal', 'Persönlich'
        SICK = 'sick', 'Krank'
        CUSTOM = 'custom', 'Benutzerdefiniert'

    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.CUSTOM)
    allow_paid = models.BooleanField(default=False)
    allow_unpaid = models.BooleanField(default=True)
    allow_past = models.BooleanField(default=False)
    ignores_notice = models.BooleanField(default=False)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = 'core'
        ordering = ['name']

    def __str__(self):
        return self.name


class TimeOffRequestDetail(TimestampedModel):
    request = models.OneToOneField(TimeOffRequest, on_delete=models.CASCADE, related_name='self_service_detail')
    time_off_type = models.ForeignKey(TimeOffType, on_delete=models.PROTECT, related_name='requests')
    all_day = models.BooleanField(default=True)
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    paid = models.BooleanField(default=False)
    paid_hours = models.DecimalField(max_digits=6, decimal_places=2, blank=True, null=True)

    class Meta:
        app_label = 'core'


class OpenShiftPolicy(TimestampedModel):
    class AudienceMode(models.TextChoices):
        ELIGIBLE = 'eligible', 'Alle berechtigten Mitarbeiter'
        SELECTED = 'selected', 'Ausgewählte Mitarbeiter'

    shift = models.OneToOneField(Shift, on_delete=models.CASCADE, related_name='open_shift_policy')
    require_approval = models.BooleanField(default=False)
    audience_mode = models.CharField(max_length=20, choices=AudienceMode.choices, default=AudienceMode.ELIGIBLE)
    selected_workers = models.ManyToManyField(WorkerProfile, related_name='targeted_open_shift_policies', blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='open_shift_policies_updated')

    class Meta:
        app_label = 'core'


class OpenShiftRequest(TimestampedModel):
    class Status(models.TextChoices):
        PENDING_APPROVAL = 'pending_approval', 'Genehmigung ausstehend'
        PENDING_ACCEPTANCE = 'pending_acceptance', 'Annahme ausstehend'
        ACCEPTED = 'accepted', 'Angenommen'
        DENIED = 'denied', 'Abgelehnt'
        DECLINED = 'declined', 'Nicht angenommen'
        CANCELED = 'canceled', 'Zurückgezogen'
        EXPIRED = 'expired', 'Abgelaufen'

    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='open_shift_requests')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='open_shift_requests')
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING_APPROVAL)
    note = models.CharField(max_length=500, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True, related_name='open_shift_requests_decided')
    decided_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        app_label = 'core'
        unique_together = ('shift', 'worker')
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'], name='open_req_status_idx')]


class ShiftCoverageRequest(TimestampedModel):
    class Kind(models.TextChoices):
        DROP = 'drop', 'Schicht abgeben'
        SWAP = 'swap', 'Schicht tauschen'

    class Status(models.TextChoices):
        PENDING_REVIEW = 'pending_review', 'Manager-Prüfung ausstehend'
        PENDING_ACCEPTANCE = 'pending_acceptance', 'Annahme ausstehend'
        ACCEPTED = 'accepted', 'Angenommen'
        DENIED = 'denied', 'Abgelehnt'
        DECLINED = 'declined', 'Nicht angenommen'
        CANCELED = 'canceled', 'Zurückgezogen'
        EXPIRED = 'expired', 'Abgelaufen'

    kind = models.CharField(max_length=20, choices=Kind.choices)
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='coverage_requests')
    requested_by = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='coverage_requests_created')
    offered_to = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, blank=True, null=True, related_name='coverage_requests_received')
    offered_shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, blank=True, null=True, related_name='swap_offers_received')
    status = models.CharField(max_length=30, choices=Status.choices)
    note = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='coverage_requests_reviewed')
    reviewed_at = models.DateTimeField(blank=True, null=True)
    accepted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        app_label = 'core'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='coverage_req_status_idx'),
            models.Index(fields=['offered_to', 'status'], name='coverage_req_recipient_idx'),
        ]
