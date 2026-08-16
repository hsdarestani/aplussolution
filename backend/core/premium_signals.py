from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Shift, TimeEntry, TimeOffRequest, User
from .premium_models import StaffCallout, TaskCompletion
from .shift_slots import ShiftSlot


def _emit(event_type, instance, extra=None):
    try:
        from .premium_services import emit_webhook
        payload = {'id': str(instance.pk), **(extra or {})}
        emit_webhook(event_type, payload)
    except Exception:
        return


@receiver(post_save, sender=User)
def user_event(sender, instance, created, **kwargs):
    _emit('users.created' if created else 'users.updated', instance, {'email': instance.email, 'role': instance.role})


@receiver(post_save, sender=Shift)
def shift_event(sender, instance, created, **kwargs):
    _emit('shifts.created' if created else 'shifts.updated', instance, {'status': instance.status, 'starts_at': instance.starts_at.isoformat()})


@receiver(post_save, sender=ShiftSlot)
def slot_event(sender, instance, created, **kwargs):
    _emit('shifts.assignment', instance, {'shift_id': str(instance.shift_id), 'worker_id': str(instance.worker_id) if instance.worker_id else None, 'status': instance.status})


@receiver(post_save, sender=TimeEntry)
def time_event(sender, instance, created, **kwargs):
    _emit('times.created' if created else 'times.updated', instance, {'worker_id': str(instance.worker_id), 'approved': instance.approved})


@receiver(post_save, sender=TimeOffRequest)
def time_off_event(sender, instance, created, **kwargs):
    _emit('time_off.created' if created else 'time_off.updated', instance, {'worker_id': str(instance.worker_id), 'status': instance.status})


@receiver(post_save, sender=StaffCallout)
def callout_event(sender, instance, created, **kwargs):
    _emit('callouts.created' if created else 'callouts.updated', instance, {'shift_id': str(instance.shift_id), 'worker_id': str(instance.worker_id), 'status': instance.status})


@receiver(post_save, sender=TaskCompletion)
def task_event(sender, instance, created, **kwargs):
    if created:
        _emit('tasks.completed', instance, {'run_id': str(instance.run_id), 'item_id': str(instance.item_id), 'completed_by': str(instance.completed_by_id) if instance.completed_by_id else None})
