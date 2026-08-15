from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .integration_v7_service import emit_webhook_event
from .models import Shift, TimeEntry, TimeOffRequest
from .payroll_models import PayPeriod, WorkerTimesheet


def _queue(event_type, payload):
    transaction.on_commit(lambda: emit_webhook_event(event_type, payload))


@receiver(post_save, sender=Shift)
def shift_event(sender, instance, created=False, **kwargs):
    _queue('shift.created' if created else 'shift.updated', {
        'id': str(instance.id), 'status': instance.status, 'starts_at': instance.starts_at.isoformat(),
        'ends_at': instance.ends_at.isoformat(), 'location_id': str(instance.location_id),
        'position_id': str(instance.position_id), 'worker_id': str(instance.worker_id) if instance.worker_id else None,
        'is_open': instance.is_open,
    })


@receiver(post_save, sender=TimeEntry)
def time_entry_event(sender, instance, created=False, **kwargs):
    _queue('time_entry.created' if created else 'time_entry.updated', {
        'id': str(instance.id), 'worker_id': str(instance.worker_id), 'shift_id': str(instance.shift_id) if instance.shift_id else None,
        'clock_in': instance.clock_in.isoformat(), 'clock_out': instance.clock_out.isoformat() if instance.clock_out else None,
        'approved': instance.approved,
    })


@receiver(post_save, sender=TimeOffRequest)
def time_off_event(sender, instance, created=False, **kwargs):
    _queue('time_off.created' if created else 'time_off.updated', {
        'id': str(instance.id), 'worker_id': str(instance.worker_id), 'starts_on': instance.starts_on.isoformat(),
        'ends_on': instance.ends_on.isoformat(), 'status': instance.status,
    })


@receiver(post_save, sender=PayPeriod)
def pay_period_event(sender, instance, created=False, **kwargs):
    _queue('pay_period.created' if created else 'pay_period.updated', {
        'id': str(instance.id), 'name': instance.name, 'starts_on': instance.starts_on.isoformat(),
        'ends_on': instance.ends_on.isoformat(), 'status': instance.status,
    })


@receiver(post_save, sender=WorkerTimesheet)
def timesheet_event(sender, instance, created=False, **kwargs):
    _queue('timesheet.created' if created else 'timesheet.updated', {
        'id': str(instance.id), 'pay_period_id': str(instance.pay_period_id), 'worker_id': str(instance.worker_id),
        'status': instance.status, 'net_minutes': instance.net_minutes,
    })
