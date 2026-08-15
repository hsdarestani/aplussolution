from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .communications_models import NotificationPreference
from .communications_service import ensure_notification_state, notify
from .models import Availability, Notification, Shift, ShiftSwapRequest, TimeOffRequest, User
from .shift_slots import ShiftSlot
from .workplace_access import has_capability


def _capture_previous(sender, instance, fields):
    if not instance.pk:
        instance._communications_previous = None
        return
    previous = sender.objects.filter(pk=instance.pk).values(*fields).first()
    instance._communications_previous = previous


def _manager_recipients(*, worker=None, capability='schedule.view'):
    users = User.objects.filter(is_active=True, role__in=[User.Role.ADMIN, User.Role.MANAGER])
    for user in users:
        if user.role == User.Role.ADMIN or has_capability(user, capability, worker=worker):
            yield user


@receiver(post_save, sender=Notification)
def attach_notification_state(sender, instance, created=False, **kwargs):
    # Legacy code still creates Notification directly. State backfill here makes those
    # notifications visible to the V6 dispatcher without changing every older module.
    ensure_notification_state(instance)


@receiver(pre_save, sender=Shift)
def capture_shift_change(sender, instance, **kwargs):
    _capture_previous(sender, instance, ['status', 'starts_at', 'ends_at', 'location_id', 'position_id'])


@receiver(post_save, sender=Shift)
def notify_shift_change(sender, instance, created=False, **kwargs):
    previous = getattr(instance, '_communications_previous', None)
    became_published = instance.status == Shift.Status.PUBLISHED and (not previous or previous['status'] != Shift.Status.PUBLISHED)
    relevant_changed = bool(previous and instance.status == Shift.Status.PUBLISHED and any(
        previous[field] != getattr(instance, field) for field in ['starts_at', 'ends_at', 'location_id', 'position_id']
    ))
    if not became_published and not relevant_changed:
        return

    claimed = instance.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user')
    for slot in claimed:
        notify(
            slot.worker.user,
            category=NotificationPreference.Category.SCHEDULE,
            kind=f'schedule-shift-{instance.id}-{instance.updated_at.timestamp()}',
            dedupe_key=f'schedule-shift-{instance.id}-{instance.updated_at.isoformat()}-{slot.worker_id}',
            title='Dienstplan aktualisiert',
            body=f'{instance.starts_at:%d.%m.%Y %H:%M} – {instance.location.name} – {instance.position.name}',
            action_url='/schedule',
            data={'shift_id': str(instance.id)},
        )

    if became_published and instance.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).exists():
        from .scheduling_rules import eligible_workers_for_shift
        for row in eligible_workers_for_shift(instance):
            if not row['eligible']:
                continue
            from .models import WorkerProfile
            worker = WorkerProfile.objects.select_related('user').filter(pk=row['worker']).first()
            if not worker:
                continue
            notify(
                worker.user,
                category=NotificationPreference.Category.OPEN_SHIFT,
                kind=f'open-shift-{instance.id}',
                dedupe_key=f'open-shift-{instance.id}-{worker.id}',
                title='Neue offene Schicht',
                body=f'{instance.starts_at:%d.%m.%Y %H:%M} – {instance.location.name} – {instance.position.name}',
                action_url='/schedule',
                data={'shift_id': str(instance.id)},
            )


@receiver(pre_save, sender=ShiftSlot)
def capture_slot_change(sender, instance, **kwargs):
    _capture_previous(sender, instance, ['worker_id', 'status'])


@receiver(post_save, sender=ShiftSlot)
def notify_slot_assignment(sender, instance, created=False, **kwargs):
    previous = getattr(instance, '_communications_previous', None)
    assigned = instance.worker_id and instance.status == ShiftSlot.Status.CLAIMED and (
        not previous or previous['worker_id'] != instance.worker_id or previous['status'] != ShiftSlot.Status.CLAIMED
    )
    if not assigned:
        return
    worker = instance.worker
    if not worker or not worker.user.is_active:
        return
    shift = instance.shift
    notify(
        worker.user,
        category=NotificationPreference.Category.SCHEDULE,
        kind=f'schedule-assigned-{instance.id}',
        dedupe_key=f'schedule-assigned-{instance.id}-{worker.id}',
        title='Schicht zugewiesen',
        body=f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name} – {shift.position.name}',
        action_url='/schedule',
        data={'shift_id': str(shift.id), 'slot_id': str(instance.id)},
    )


@receiver(pre_save, sender=TimeOffRequest)
def capture_time_off(sender, instance, **kwargs):
    _capture_previous(sender, instance, ['status'])


@receiver(post_save, sender=TimeOffRequest)
def notify_time_off(sender, instance, created=False, **kwargs):
    if created:
        for manager in _manager_recipients(worker=instance.worker, capability='attendance.edit'):
            notify(
                manager,
                category=NotificationPreference.Category.TIME_OFF,
                kind=f'time-off-request-{instance.id}',
                dedupe_key=f'time-off-request-{instance.id}-{manager.id}',
                title='Neuer Abwesenheitsantrag',
                body=f'{instance.worker.user.get_full_name() or instance.worker.user.email}: {instance.starts_on:%d.%m.%Y} – {instance.ends_on:%d.%m.%Y}',
                action_url='/time',
                data={'time_off_id': str(instance.id), 'worker_id': str(instance.worker_id)},
            )
        return
    previous = getattr(instance, '_communications_previous', None)
    if previous and previous['status'] != instance.status and instance.status in {TimeOffRequest.Status.APPROVED, TimeOffRequest.Status.REJECTED}:
        notify(
            instance.worker.user,
            category=NotificationPreference.Category.TIME_OFF,
            kind=f'time-off-decision-{instance.id}-{instance.status}',
            dedupe_key=f'time-off-decision-{instance.id}-{instance.status}',
            title='Abwesenheitsantrag entschieden',
            body='Genehmigt' if instance.status == TimeOffRequest.Status.APPROVED else 'Abgelehnt',
            action_url='/time',
            data={'time_off_id': str(instance.id), 'status': instance.status},
        )


@receiver(post_save, sender=Availability)
def notify_availability(sender, instance, created=False, **kwargs):
    for manager in _manager_recipients(worker=instance.worker, capability='schedule.view'):
        notify(
            manager,
            category=NotificationPreference.Category.AVAILABILITY,
            kind=f'availability-{instance.id}-{instance.updated_at.timestamp()}',
            dedupe_key=f'availability-{instance.id}-{instance.updated_at.isoformat()}-{manager.id}',
            title='Verfügbarkeit geändert',
            body=instance.worker.user.get_full_name() or instance.worker.user.email,
            action_url='/operations',
            data={'availability_id': str(instance.id), 'worker_id': str(instance.worker_id)},
        )


@receiver(pre_save, sender=ShiftSwapRequest)
def capture_swap(sender, instance, **kwargs):
    _capture_previous(sender, instance, ['status', 'offered_to_id'])


@receiver(post_save, sender=ShiftSwapRequest)
def notify_swap(sender, instance, created=False, **kwargs):
    if created:
        recipients = list(_manager_recipients(worker=instance.requested_by, capability='schedule.edit'))
        if instance.offered_to_id:
            recipients.append(instance.offered_to.user)
        seen = set()
        for recipient in recipients:
            if recipient.id in seen:
                continue
            seen.add(recipient.id)
            notify(
                recipient,
                category=NotificationPreference.Category.SWAP_DROP,
                kind=f'swap-request-{instance.id}',
                dedupe_key=f'swap-request-{instance.id}-{recipient.id}',
                title='Neue Tauschanfrage',
                body=instance.requested_by.user.get_full_name() or instance.requested_by.user.email,
                action_url='/operations',
                data={'swap_id': str(instance.id)},
            )
        return
    previous = getattr(instance, '_communications_previous', None)
    if previous and previous['status'] != instance.status:
        notify(
            instance.requested_by.user,
            category=NotificationPreference.Category.SWAP_DROP,
            kind=f'swap-decision-{instance.id}-{instance.status}',
            dedupe_key=f'swap-decision-{instance.id}-{instance.status}-{instance.requested_by.user_id}',
            title='Tauschanfrage aktualisiert',
            body=instance.get_status_display(),
            action_url='/operations',
            data={'swap_id': str(instance.id), 'status': instance.status},
        )
