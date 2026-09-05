from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.management import call_command
from django.utils import timezone

from .document_center import dispatch_contract_reminders
from .models import IntegrationSyncRun, Notification, Shift, ShiftImportPackage
from .operational_notifications import dispatch_attendance_reminders
from .shift_slots import ShiftSlot
from .wiw import WhenIWorkError


WIW_FULL_RECONCILE_INTERVAL = timedelta(hours=24)
WIW_FULL_RECONCILE_LOCK_KEY = 'wiw:full-reconciliation:queued'
WIW_FULL_RECONCILE_LOCK_SECONDS = 2 * 60 * 60


def _reapply_schedule_worker_config(run):
    """Keep business-owned Dienstplan worker rules authoritative over WIW imports."""
    if getattr(run, 'status', '') == 'success':
        call_command('configure_schedule_workers')


def _queue_full_wiw_reconciliation_if_due():
    """Queue an all-time WIW reconciliation when the last verified pass is stale.

    The normal five-minute sync keeps current operations fresh. This second
    safety net walks the complete WIW history/future range and proves that every
    remote record exists locally, so a temporary API gap cannot become a
    permanent missing shift. A short cache lock prevents duplicate heavy jobs.
    """
    if not settings.WIW_SYNC_ENABLED:
        return False

    cutoff = timezone.now() - WIW_FULL_RECONCILE_INTERVAL
    recent_verified = IntegrationSyncRun.objects.filter(
        provider='wiw',
        mode='final_full',
        status=IntegrationSyncRun.Status.SUCCESS,
        finished_at__gte=cutoff,
    ).exists()
    if recent_verified:
        return False

    if not cache.add(WIW_FULL_RECONCILE_LOCK_KEY, 'queued', timeout=WIW_FULL_RECONCILE_LOCK_SECONDS):
        return False

    reconcile_when_i_work_full.delay()
    return True


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
def reconcile_when_i_work_full(self):
    """Backfill and verify the complete WIW dataset from old history to future.

    ``build_wiw_migration_report`` already fetches dynamic WIW resources in
    bounded windows from 2000 through 2100, imports them transactionally, and
    compares remote/local identities afterwards. We keep that proven path as a
    recurring self-healing reconciliation instead of relying on a one-time
    migration pass.
    """
    if not settings.WIW_SYNC_ENABLED:
        return {'status': 'disabled', 'complete': False}

    from .wiw_migration import build_wiw_migration_report

    report = build_wiw_migration_report(apply_full_sync=True)
    sync = report.get('sync') or {}
    incomplete = [
        name
        for name, row in (report.get('resources') or {}).items()
        if not row.get('complete')
    ]
    if sync.get('status') != IntegrationSyncRun.Status.SUCCESS or not report.get('complete'):
        raise WhenIWorkError(
            'WIW full reconciliation incomplete: '
            + (', '.join(incomplete) if incomplete else str(sync.get('errors') or 'unknown error'))
        )

    # Full imports touch WIW-owned workforce data, so immediately restore the
    # locally approved operational worker scope afterwards.
    call_command('configure_schedule_workers')
    cache.delete(WIW_FULL_RECONCILE_LOCK_KEY)
    return {
        'status': 'success',
        'complete': True,
        'sync_id': sync.get('id'),
        'history_window': report.get('history_window'),
        'resources': {
            name: {
                'remote_count': row.get('remote_count', 0),
                'local_count': row.get('local_count', 0),
                'missing_local_count': row.get('missing_local_count', 0),
            }
            for name, row in (report.get('resources') or {}).items()
        },
    }


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
    full_reconciliation_queued = _queue_full_wiw_reconciliation_if_due()
    return {
        'id': str(run.id),
        'status': run.status,
        'counts': run.counts,
        'errors': run.errors,
        'full_reconciliation_queued': full_reconciliation_queued,
    }


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
        _queue_full_wiw_reconciliation_if_due()
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
