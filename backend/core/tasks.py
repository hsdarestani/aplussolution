from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.core.management import call_command
from django.utils import timezone

from .document_center import dispatch_contract_reminders
from .models import Notification, Shift, ShiftImportPackage
from .operational_notifications import dispatch_attendance_reminders
from .shift_slots import ShiftSlot


def _reapply_schedule_worker_config(run):
    """Keep business-owned Dienstplan worker rules authoritative over WIW imports."""
    if getattr(run, 'status', '') == 'success':
        call_command('configure_schedule_workers')


@shared_task
def send_contract_reminders():
    """Dispatch contract reminders while preserving the historical integer task result."""
    return dispatch_contract_reminders()['notifications']


@shared_task
def send_attendance_reminders():
    return dispatch_attendance_reminders()


@shared_task
def send_shift_reminders():
    now = timezone.now()
    slots = ShiftSlot.objects.filter(
        status=ShiftSlot.Status.CLAIMED,
        worker__isnull=False,
        shift__starts_at__range=(
            now + timedelta(hours=23, minutes=30),
            now + timedelta(hours=24, minutes=30),
        ),
        shift__status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
    ).select_related('worker__user', 'shift__location', 'shift__position')
    count = 0
    for slot in slots:
        shift = slot.shift
        user = slot.worker.user
        local_start = timezone.localtime(shift.starts_at)
        _, created = Notification.objects.get_or_create(
            user=user,
            kind=f'shift-24h-{slot.id}',
            defaults={
                'action_url': '/schedule',
                'title': 'Dein Einsatz beginnt morgen',
                'body': f'{local_start:%d.%m.%Y %H:%M} – {shift.location.name} – {shift.position.name}',
            },
        )
        count += int(created)
        if created and user.email:
            send_mail(
                'A+ Solution: Dein Einsatz beginnt morgen',
                f'{local_start:%d.%m.%Y %H:%M}\n{shift.location.name}\n{shift.position.name}',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=True,
            )
    return count


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def sync_when_i_work(self, mode='incremental', triggered_by_id=None):
    """Refresh the temporary one-way WIW -> A+ migration feed."""
    if not settings.WIW_SYNC_ENABLED:
        return {'status': 'disabled', 'counts': {}, 'errors': []}
    from .models import User
    from .wiw_schedule_sync import WhenIWorkSynchronizer
    user = User.objects.filter(pk=triggered_by_id).first() if triggered_by_id else None
    run = WhenIWorkSynchronizer(triggered_by=user).sync(mode=mode)
    _reapply_schedule_worker_config(run)
    return {'id': str(run.id), 'status': run.status, 'counts': run.counts, 'errors': run.errors}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def process_wiw_webhook(self, event_id):
    from .models import WebhookEvent
    event = WebhookEvent.objects.get(pk=event_id)
    if not settings.WIW_SYNC_ENABLED:
        event.processed_at = timezone.now()
        event.processing_error = 'WIW sync disabled; A+ Workforce is source of truth.'
        event.save(update_fields=['processed_at', 'processing_error', 'updated_at'])
        return {'event': str(event.id), 'status': 'ignored'}
    from .wiw_schedule_sync import WhenIWorkSynchronizer
    try:
        run = WhenIWorkSynchronizer().sync(mode='incremental')
        _reapply_schedule_worker_config(run)
        event.processed_at = timezone.now()
        event.processing_error = ''
        event.save(update_fields=['processed_at', 'processing_error', 'updated_at'])
        return {'event': str(event.id), 'sync': str(run.id), 'status': run.status}
    except Exception as exc:
        event.processing_error = str(exc)
        event.save(update_fields=['processing_error', 'updated_at'])
        raise


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def generate_due_client_contracts(self):
    from .native_cutover import generate_client_contract
    now = timezone.now()
    packages = ShiftImportPackage.objects.filter(
        status=ShiftImportPackage.Status.PENDING,
        first_shift_time__lte=now + timedelta(hours=24),
        first_shift_time__gte=now - timedelta(days=1),
        client__isnull=False,
    ).select_related('client', 'contract')
    generated = skipped = 0
    errors = []
    for package in packages:
        try:
            generate_client_contract(package)
            generated += 1
        except ValueError as exc:
            skipped += 1
            errors.append({'package': str(package.id), 'error': str(exc)})
    return {'generated': generated, 'skipped': skipped, 'errors': errors}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def sync_working_time_current_year(self):
    from .native_cutover import sync_working_time
    today = timezone.localdate()
    log = sync_working_time(today.replace(month=1, day=1), today)
    return {'id': str(log.id), 'status': log.status, 'records_count': log.records_count}


@shared_task
def backup_working_time():
    from .working_time import create_backup
    return create_backup('weekly')