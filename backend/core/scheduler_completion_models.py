from django.conf import settings
from django.db import models

from .models import Location, Position, Shift, TimestampedModel, User, WorkerProfile
from .scheduling_models import ScheduleGroup
from .shift_slots import ShiftSlot


class ScheduleAnnotation(TimestampedModel):
    class Kind(models.TextChoices):
        ANNOUNCEMENT = 'announcement', 'Ankündigung'
        BUSINESS_CLOSED = 'business_closed', 'Betrieb geschlossen'
        BLOCK_TIME_OFF = 'block_time_off', 'Keine Abwesenheit zulassen'

    class ClosedShiftAction(models.TextChoices):
        LEAVE = 'leave', 'Schichten unverändert lassen'
        UNPUBLISH = 'unpublish', 'Unbelegte Schichten zurückziehen'
        OPEN = 'open', 'Belegte Schichten als OpenShift freigeben'
        DELETE = 'delete', 'Zukünftige Schichten löschen'

    kind = models.CharField(max_length=30, choices=Kind.choices, default=Kind.ANNOUNCEMENT)
    title = models.CharField(max_length=180)
    message = models.TextField(blank=True)
    starts_on = models.DateField()
    ends_on = models.DateField()
    schedule = models.ForeignKey(ScheduleGroup, on_delete=models.CASCADE, related_name='annotations', blank=True, null=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='schedule_annotations', blank=True, null=True)
    business_closed_action = models.CharField(max_length=20, choices=ClosedShiftAction.choices, default=ClosedShiftAction.LEAVE)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='schedule_annotations_created', blank=True, null=True)

    class Meta:
        app_label = 'core'
        ordering = ['starts_on', 'title']
        indexes = [models.Index(fields=['active', 'starts_on', 'ends_on'], name='sched_annot_range_idx')]

    def __str__(self):
        return f'{self.title} ({self.starts_on:%d.%m.%Y})'


class ScheduleTaskList(TimestampedModel):
    title = models.CharField(max_length=180)
    work_date = models.DateField()
    notes = models.TextField(blank=True)
    schedule = models.ForeignKey(ScheduleGroup, on_delete=models.CASCADE, related_name='task_lists', blank=True, null=True)
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='schedule_task_lists', blank=True, null=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='schedule_task_lists_created', blank=True, null=True)

    class Meta:
        app_label = 'core'
        ordering = ['work_date', 'title']
        indexes = [models.Index(fields=['active', 'work_date'], name='sched_tasklist_date_idx')]

    def __str__(self):
        return f'{self.work_date:%d.%m.%Y} – {self.title}'


class ScheduleTask(TimestampedModel):
    task_list = models.ForeignKey(ScheduleTaskList, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=220)
    position = models.ForeignKey(Position, on_delete=models.SET_NULL, related_name='schedule_tasks', blank=True, null=True)
    assignee = models.ForeignKey(WorkerProfile, on_delete=models.SET_NULL, related_name='schedule_tasks', blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name='schedule_tasks_completed', blank=True, null=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = 'core'
        ordering = ['sort_order', 'created_at']
        indexes = [models.Index(fields=['assignee', 'completed_at'], name='sched_task_assignee_idx')]

    @property
    def completed(self):
        return self.completed_at is not None


class ShiftConfirmation(TimestampedModel):
    slot = models.OneToOneField(ShiftSlot, on_delete=models.CASCADE, related_name='confirmation')
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name='confirmations')
    worker = models.ForeignKey(WorkerProfile, on_delete=models.CASCADE, related_name='shift_confirmations')
    publication_at = models.DateTimeField(blank=True, null=True)
    requested_at = models.DateTimeField()
    confirmed_at = models.DateTimeField(blank=True, null=True)
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='shift_confirmations_completed', blank=True, null=True)

    class Meta:
        app_label = 'core'
        ordering = ['shift__starts_at', 'worker__employee_number']
        indexes = [models.Index(fields=['worker', 'confirmed_at'], name='shift_confirm_worker_idx')]

    @property
    def status(self):
        return 'confirmed' if self.confirmed_at else 'pending'


class SchedulerDisplayPreference(TimestampedModel):
    class ColorMode(models.TextChoices):
        SHIFT = 'shift', 'Schichtfarbe'
        POSITION = 'position', 'Position'
        LOCATION = 'location', 'Einsatzort / Job Site'

    class TimezoneMode(models.TextChoices):
        WORKPLACE = 'workplace', 'Betriebszeitzone'
        SCHEDULE = 'schedule', 'Dienstplan-Zeitzone'
        LOCAL = 'local', 'Lokale Zeitzone'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='scheduler_display_preference')
    color_mode = models.CharField(max_length=20, choices=ColorMode.choices, default=ColorMode.POSITION)
    timezone_mode = models.CharField(max_length=20, choices=TimezoneMode.choices, default=TimezoneMode.WORKPLACE)
    local_timezone = models.CharField(max_length=64, default='Europe/Berlin')

    class Meta:
        app_label = 'core'
