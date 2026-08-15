from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .communications_models import NotificationDelivery, NotificationPreference, NotificationState
from .communications_service import dispatch_notification_now, ensure_notification_state, notify
from .models import Notification, Shift
from .shift_slots import ShiftSlot


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 4})
def dispatch_notification(self, notification_id):
    notification = Notification.objects.select_related('user').filter(pk=notification_id).first()
    if not notification:
        return {'status': 'missing'}
    return dispatch_notification_now(notification)


@shared_task
def dispatch_pending_notifications():
    pending = Notification.objects.filter(
        delivery_state__deleted_at__isnull=True,
    ).exclude(delivery_state__data__legacy_backfill=True).select_related('user', 'delivery_state').order_by('created_at')[:250]
    count = 0
    for notification in pending:
        state = ensure_notification_state(notification)
        expected = {
            NotificationDelivery.Channel.PUSH,
            NotificationDelivery.Channel.EMAIL,
            NotificationDelivery.Channel.SMS,
        }
        existing = set(notification.delivery_attempts.values_list('channel', flat=True))
        retryable = notification.delivery_attempts.filter(
            status__in=[NotificationDelivery.Status.PENDING, NotificationDelivery.Status.FAILED]
        ).exists()
        if expected - existing or retryable:
            dispatch_notification.delay(str(notification.id))
            count += 1
    return {'queued': count}


@shared_task
def send_configured_shift_reminders():
    from .communications_service import get_preference
    from .models import WorkerProfile

    now = timezone.now()
    sent = 0
    workers = WorkerProfile.objects.filter(active=True, user__is_active=True).select_related('user')
    for worker in workers:
        pref = get_preference(worker.user, NotificationPreference.Category.SHIFT_REMINDER)
        if not (pref.in_app_enabled or pref.push_enabled or pref.email_enabled or pref.sms_enabled):
            continue
        minutes = max(1, min(int(pref.reminder_minutes or 1440), 1440))
        target = now + timedelta(minutes=minutes)
        window_start = target - timedelta(minutes=7)
        window_end = target + timedelta(minutes=7)
        slots = ShiftSlot.objects.filter(
            worker=worker,
            status=ShiftSlot.Status.CLAIMED,
            shift__starts_at__range=(window_start, window_end),
            shift__status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        ).select_related('shift__location', 'shift__position')
        for slot in slots:
            shift = slot.shift
            notification = notify(
                worker.user,
                category=NotificationPreference.Category.SHIFT_REMINDER,
                kind=f'shift-reminder-{minutes}-{slot.id}',
                dedupe_key=f'shift-reminder-{minutes}-{slot.id}',
                title='Dein Einsatz beginnt bald',
                body=f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name} – {shift.position.name}',
                action_url='/schedule',
                data={'shift_id': str(shift.id), 'minutes_before': minutes},
            )
            sent += int(notification is not None)
    return {'notifications': sent}
