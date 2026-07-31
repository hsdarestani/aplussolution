from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .document_center import dispatch_contract_reminders
from .models import Notification, Shift


@shared_task
def send_contract_reminders():
    """Dispatch contract deadline/signature reminders through the shared document-center engine."""
    return dispatch_contract_reminders()


@shared_task
def send_shift_reminders():
    now = timezone.now()
    shifts = Shift.objects.filter(
        starts_at__range=(
            now + timedelta(hours=23, minutes=30),
            now + timedelta(hours=24, minutes=30),
        ),
        worker__isnull=False,
        status__in=['published', 'confirmed'],
    ).select_related('worker__user', 'location', 'position')
    count = 0
    for shift in shifts:
        _, created = Notification.objects.get_or_create(
            user=shift.worker.user,
            kind=f'shift-24h-{shift.id}',
            defaults={
                'action_url': '/schedule',
                'title': 'Dein Einsatz beginnt morgen',
                'body': f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name} – {shift.position.name}',
            },
        )
        count += int(created)
        if created and shift.worker.user.email:
            send_mail(
                'A+ Solution: Dein Einsatz beginnt morgen',
                f'{shift.starts_at:%d.%m.%Y %H:%M}\n{shift.location.name}\n{shift.position.name}',
                settings.DEFAULT_FROM_EMAIL,
                [shift.worker.user.email],
                fail_silently=True,
            )
    return count


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def sync_when_i_work(self, mode='incremental', triggered_by_id=None):
    from .models import User
    from .wiw_sync import WhenIWorkSynchronizer
    user = User.objects.filter(pk=triggered_by_id).first() if triggered_by_id else None
    run = WhenIWorkSynchronizer(triggered_by=user).sync(mode=mode)
    return {'id': str(run.id), 'status': run.status, 'counts': run.counts, 'errors': run.errors}


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def process_wiw_webhook(self, event_id):
    from .models import WebhookEvent
    from .wiw_sync import WhenIWorkSynchronizer
    event = WebhookEvent.objects.get(pk=event_id)
    try:
        run = WhenIWorkSynchronizer().sync(mode='incremental')
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
    from .order_automation import generate_due_client_contracts as run
    return run()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 3})
def sync_working_time_current_year(self):
    from .working_time import sync_working_time
    today = timezone.localdate()
    log = sync_working_time(today.replace(month=1, day=1), today)
    return {'id': str(log.id), 'status': log.status, 'records_count': log.records_count}


@shared_task
def backup_working_time():
    from .working_time import create_backup
    return create_backup('weekly')
