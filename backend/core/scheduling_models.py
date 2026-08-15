from django.db import models

from .models import Location, Position, TimestampedModel, WorkerProfile


class ScheduleGroup(TimestampedModel):
    """WIW-style schedule boundary used for memberships, timezone and planning scope."""

    name = models.CharField(max_length=160, unique=True)
    timezone = models.CharField(max_length=64, default='Europe/Berlin')
    locations = models.ManyToManyField(Location, related_name='schedule_groups', blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        app_label = 'core'
        ordering = ['name']

    def __str__(self):
        return self.name


class ScheduleMembership(TimestampedModel):
    schedule = models.ForeignKey(ScheduleGroup, on_delete=models.CASCADE, related_name='memberships')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='schedule_memberships')
    active = models.BooleanField(default=True)
    primary = models.BooleanField(default=False)

    class Meta:
        app_label = 'core'
        unique_together = ('schedule', 'worker')
        ordering = ['schedule__name', 'worker__employee_number']


class WorkerPositionQualification(TimestampedModel):
    class Level(models.TextChoices):
        TRAINEE = 'trainee', 'In Einarbeitung'
        QUALIFIED = 'qualified', 'Qualifiziert'
        LEAD = 'lead', 'Leitung'

    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='position_qualifications')
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='worker_qualifications')
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.QUALIFIED)
    active = models.BooleanField(default=True)
    expires_on = models.DateField(blank=True, null=True)
    note = models.CharField(max_length=250, blank=True)

    class Meta:
        app_label = 'core'
        unique_together = ('worker', 'position')
        ordering = ['worker__employee_number', 'position__name']


class SkillTag(TimestampedModel):
    name = models.CharField(max_length=120, unique=True)
    color = models.CharField(max_length=20, default='#155eef')
    active = models.BooleanField(default=True)

    class Meta:
        app_label = 'core'
        ordering = ['name']

    def __str__(self):
        return self.name


class WorkerSkillTag(TimestampedModel):
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='skill_tags')
    tag = models.ForeignKey(SkillTag, on_delete=models.CASCADE, related_name='worker_links')
    verified = models.BooleanField(default=True)
    expires_on = models.DateField(blank=True, null=True)
    note = models.CharField(max_length=250, blank=True)

    class Meta:
        app_label = 'core'
        unique_together = ('worker', 'tag')
        ordering = ['worker__employee_number', 'tag__name']


class PositionSkillTag(TimestampedModel):
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='required_tag_links')
    tag = models.ForeignKey(SkillTag, on_delete=models.CASCADE, related_name='position_links')
    required = models.BooleanField(default=True)

    class Meta:
        app_label = 'core'
        unique_together = ('position', 'tag')
        ordering = ['position__name', 'tag__name']


class SchedulingPolicy(TimestampedModel):
    class Enforcement(models.TextChoices):
        OFF = 'off', 'Aus'
        WARN = 'warn', 'Warnen'
        BLOCK = 'block', 'Blockieren'

    name = models.CharField(max_length=160, unique=True)
    active = models.BooleanField(default=True)
    schedule = models.ForeignKey(ScheduleGroup, on_delete=models.CASCADE, related_name='policies', blank=True, null=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='scheduling_policies', blank=True, null=True)
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='scheduling_policies', blank=True, null=True)

    min_rest_hours = models.DecimalField(max_digits=5, decimal_places=2, default=11)
    max_days_per_week = models.PositiveSmallIntegerField(default=6)
    max_consecutive_days = models.PositiveSmallIntegerField(default=6)
    max_weekly_hours = models.DecimalField(max_digits=6, decimal_places=2, default=48)

    qualification_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.WARN)
    schedule_membership_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.OFF)
    skill_tag_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.WARN)
    availability_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.BLOCK)
    time_off_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.BLOCK)
    rest_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.WARN)
    hours_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.WARN)
    days_mode = models.CharField(max_length=10, choices=Enforcement.choices, default=Enforcement.WARN)

    class Meta:
        app_label = 'core'
        ordering = ['name']

    def __str__(self):
        return self.name


class ScheduleTemplate(TimestampedModel):
    name = models.CharField(max_length=180)
    schedule = models.ForeignKey(ScheduleGroup, on_delete=models.SET_NULL, related_name='templates', blank=True, null=True)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['name']

    def __str__(self):
        return self.name


class ScheduleTemplateItem(TimestampedModel):
    template = models.ForeignKey(ScheduleTemplate, on_delete=models.CASCADE, related_name='items')
    weekday = models.PositiveSmallIntegerField(help_text='0=Montag, 6=Sonntag')
    start_time = models.TimeField()
    end_time = models.TimeField()
    client = models.ForeignKey('core.ClientCompany', on_delete=models.CASCADE, related_name='schedule_template_items')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='schedule_template_items')
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='schedule_template_items')
    required_count = models.PositiveIntegerField(default=1)
    break_minutes = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        app_label = 'core'
        ordering = ['weekday', 'start_time']
