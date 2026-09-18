from datetime import datetime, time, timedelta
from uuid import uuid4

import redis
from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage, get_connection, send_mail
from django.core.management import call_command
from django.utils import timezone

from .document_center import dispatch_contract_reminders
from .models import Notification, Shift, ShiftImportPackage, TimeEntry
from .operational_notifications import dispatch_attendance_reminders
from .shift_slots import ShiftSlot


WIW_RECONCILIATION_LOCK_KEY = 'wiw:reconciliation:exclusive:v2'
WIW_RECONCILIATION_LOCK_SECONDS = 60 * 60
WIW_RECONCILIATION_BUSY_RETRY_SECONDS = 5 * 60
WIW_RECONCILIATION_BUSY_MAX_RETRIES = 12


def _redis_client():
    return redis.Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)


def _acquire_wiw_reconciliation_lock():
    token = uuid4().hex
    acquired = _redis_client().set(
        WIW_RECONCILIATION_LOCK_KEY,
        token,
        nx=True,
        ex=WIW_RECONCILIATION_LOCK_SECONDS,
    )
    return token if acquired else None


def _release_wiw_reconciliation_lock(token):
    # Compare-and-delete keeps an expired/reacquired lock owned by another task safe.
    _redis_client().eval(
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end",
        1,
        WIW_RECONCILIATION_LOCK_KEY,
        token,
    )


def _retry_wiw_reconciliation_when_busy(task):
    raise task.retry(
        exc=RuntimeError('Another WIW reconciliation is still running.'),
        countdown=WIW_RECONCILIATION_BUSY_RETRY_SECONDS,
        max_retries=WIW_RECONCILIATION_BUSY_MAX_RETRIES,
    )


def _reapply_schedule_worker_config(run=None):
    """Keep business-owned Dienstplan worker rules authoritative over WIW imports."""
    if run is None or getattr(run, 'status', '') == 'success':
        call_command('configure_schedule_workers')


def _ensure_schedule_worker_stubs(rows, synchronizer):
    """Preserve assignments for historical WIW users no longer returned by /users."""
    from .models import User, WorkerProfile
    from .wiw_sync import as_id, first, synthetic_email

    user_ids = {
        user_id
        for item in rows
        if (user_id := as_id(first(item, 'user_id', 'user')))
    }
    if not user_ids:
        return 0

    existing = {
        str(value)
        for value in WorkerProfile.objects.exclude(wiw_user_id__isnull=True)
        .exclude(wiw_user_id='')
        .values_list('wiw_user_id', flat=True)
    }
    missing = sorted(user_ids - existing - set(synchronizer.workers))
    for wiw_user_id in missing:
        email = synthetic_email(wiw_user_id)
        user = User.objects.filter(wiw_id=wiw_user_id).first() or User.objects.filter(email=email).first()
        if not user:
            user = User(
                email=email,
                username=email,
                role=User.Role.WORKER,
                is_active=False,
                is_onboarded=False,
            )
            user.set_unusable_password()
        user.wiw_id = wiw_user_id
        user.wiw_payload = {
            **(user.wiw_payload or {}),
            'historical_archive_stub': True,
            'source': 'wiw_shifts',
        }
        user.wiw_synced_at = timezone.now()
        user.save()

        worker, _ = WorkerProfile.objects.get_or_create(
            user=user,
            defaults={
                'employee_number': f'WIW-HIST-{wiw_user_id}'[:50],
                'active': False,
                'wiw_user_id': wiw_user_id,
                'wiw_payload': {'historical_archive_stub': True, 'source': 'wiw_shifts'},
                'wiw_synced_at': timezone.now(),
            },
        )
        if not worker.wiw_user_id:
            worker.wiw_user_id = wiw_user_id
            worker.save(update_fields=['wiw_user_id', 'updated_at'])
        synchronizer.workers[wiw_user_id] = worker
    return len(missing)


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


@shared_task
def send_shift_time_report_prompts():
    """Ask assigned workers for actual hours after a shift has ended.

    The 48-hour scan window makes the task resilient to worker/beat downtime;
    get_or_create keeps the push idempotent across repeated scans.
    """
    now = timezone.now()
    shifts = Shift.objects.filter(
        ends_at__lte=now - timedelta(minutes=30),
        ends_at__gte=now - timedelta(hours=48),
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED, Shift.Status.COMPLETED],
    ).select_related('worker__user', 'location', 'position').prefetch_related('slots__worker__user')

    created_count = 0
    for shift in shifts:
        workers = {}
        if shift.worker_id and shift.worker and shift.worker.active and shift.worker.user.is_active:
            workers[str(shift.worker_id)] = shift.worker
        for slot in shift.slots.all():
            if (
                slot.status == ShiftSlot.Status.CLAIMED
                and slot.worker_id
                and slot.worker
                and slot.worker.active
                and slot.worker.user.is_active
            ):
                workers[str(slot.worker_id)] = slot.worker

        if not workers:
            continue
        local_start = timezone.localtime(shift.starts_at)
        local_end = timezone.localtime(shift.ends_at)
        for worker in workers.values():
            if TimeEntry.objects.filter(worker=worker, shift=shift).exists():
                continue
            _, created = Notification.objects.get_or_create(
                user=worker.user,
                kind=f'shift-time-report-{shift.id}-{worker.id}',
                defaults={
                    'title': 'Wie lange hast du heute gearbeitet?',
                    'body': f'{local_start:%d.%m.%Y} · geplant {local_start:%H:%M}–{local_end:%H:%M} · {shift.location.name}',
                    'action_url': '/time',
                },
            )
            created_count += int(created)
    return created_count


def _assigned_workers_for_shift(shift):
    workers = {}
    if shift.worker_id and shift.worker and shift.worker.active and shift.worker.user.is_active:
        workers[str(shift.worker_id)] = shift.worker
    for slot in shift.slots.all():
        if (
            slot.status == ShiftSlot.Status.CLAIMED
            and slot.worker_id
            and slot.worker
            and slot.worker.active
            and slot.worker.user.is_active
        ):
            workers[str(slot.worker_id)] = slot.worker
    return list(workers.values())


def _missing_month_entries(now):
    local_now = timezone.localtime(now)
    month_start = timezone.make_aware(datetime.combine(local_now.date().replace(day=1), time.min), timezone.get_current_timezone())
    shifts = Shift.objects.filter(
        ends_at__gte=month_start,
        ends_at__lte=now,
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED, Shift.Status.COMPLETED],
    ).select_related('worker__user', 'location', 'position').prefetch_related('slots__worker__user').order_by('starts_at')

    result = {}
    for shift in shifts:
        for worker in _assigned_workers_for_shift(shift):
            if TimeEntry.objects.filter(worker=worker, shift=shift).exists():
                continue
            bucket = result.setdefault(str(worker.id), {'worker': worker, 'shifts': []})
            bucket['shifts'].append(shift)
    return result


def _missing_shift_lines(shifts, limit=None):
    rows = []
    selected = shifts[:limit] if limit else shifts
    for shift in selected:
        start = timezone.localtime(shift.starts_at)
        end = timezone.localtime(shift.ends_at)
        rows.append(f'{start:%d.%m.} · {start:%H:%M}–{end:%H:%M} · {shift.position.name} · {shift.location.name}')
    if limit and len(shifts) > limit:
        rows.append(f'+ {len(shifts) - limit} weitere fehlende Schicht(en)')
    return rows


def _send_required_worker_email(subject, body, recipient):
    if not recipient:
        return 0
    if not settings.EMAIL_HOST:
        return send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=True)
    connection = get_connection(
        'django.core.mail.backends.smtp.EmailBackend',
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
        fail_silently=True,
    )
    return EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], connection=connection).send(fail_silently=True)


@shared_task
def send_monthly_missing_time_reminders():
    """Remind workers on the 28th/29th by push and on the 30th by email."""
    now = timezone.now()
    local_now = timezone.localtime(now)
    if local_now.day not in {28, 29, 30}:
        return {'day': local_now.day, 'workers': 0, 'notifications': 0, 'emails': 0}

    missing = _missing_month_entries(now)
    month_key = local_now.strftime('%Y-%m')
    notifications = 0
    emails = 0

    for payload in missing.values():
        worker = payload['worker']
        shifts = payload['shifts']
        if not shifts:
            continue
        first_shift = shifts[0]
        deep_link = f'/schedule?missing_shift={first_shift.id}&missing_month={month_key}'
        lines = _missing_shift_lines(shifts, limit=4)

        if local_now.day in {28, 29}:
            _, created = Notification.objects.get_or_create(
                user=worker.user,
                kind=f'monthly-missing-time-{month_key}-{local_now.day}-{worker.id}',
                defaults={
                    'title': 'Arbeitszeiten fehlen noch',
                    'body': 'Bitte ergänze deine Arbeitszeiten:\n' + '\n'.join(lines),
                    'action_url': deep_link,
                },
            )
            notifications += int(created)

        if local_now.day == 30 and worker.user.email:
            mail_key = f'aplus:missing-time-email:{month_key}:{worker.id}'
            if _redis_client().set(mail_key, '1', nx=True, ex=40 * 24 * 60 * 60):
                all_lines = _missing_shift_lines(shifts)
                link = f"{settings.APP_URL.rstrip('/')}/?view=schedule&missing_shift={first_shift.id}&missing_month={month_key}"
                subject = 'A+ Solution: Bitte fehlende Arbeitszeiten für diesen Monat ergänzen'
                body = (
                    f'Hallo {worker.user.first_name or worker.user.get_full_name() or "Mitarbeiter/in"},\n\n'
                    'für diesen Monat fehlen noch Arbeitszeiten zu folgenden Schichten:\n\n'
                    + '\n'.join(f'- {line}' for line in all_lines)
                    + '\n\nBitte trage die tatsächlichen Beginn- und Endzeiten unbedingt vollständig ein.\n'
                    + f'Direkt öffnen: {link}\n\nA+ Solution GmbH'
                )
                emails += int(bool(_send_required_worker_email(subject, body, worker.user.email)))

    return {'day': local_now.day, 'workers': len(missing), 'notifications': notifications, 'emails': emails}


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


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 4})
def reconcile_when_i_work_schedule(self):
    """Self-heal every API-visible WIW shift, regardless of age or future date."""
    if not settings.WIW_SYNC_ENABLED:
        return {'status': 'disabled', 'resource': 'shifts'}
    lock_token = _acquire_wiw_reconciliation_lock()
    if not lock_token:
        return _retry_wiw_reconciliation_when_busy(self)

    try:
        from .wiw import WhenIWorkClient, WhenIWorkError
        from .wiw_schedule_sync import WhenIWorkSynchronizer, fetch_complete_schedule_snapshot
        from .wiw_sync import as_id, first

        client = WhenIWorkClient()
        synchronizer = WhenIWorkSynchronizer(client=client)

        # Refresh current dependency metadata first. Historical users that WIW no
        # longer exposes are preserved below as inactive stubs so old assignments
        # can never be converted into fake OpenShifts.
        synchronizer.sync_users(client.collection('users', params={'limit': 1000}).items)
        synchronizer.sync_positions(client.collection('positions', params={'limit': 1000}, optional=True).items)
        synchronizer.sync_locations(client.collection('locations', params={'limit': 1000}, optional=True).items)
        synchronizer.sync_sites(client.collection('sites', params={'limit': 1000}, optional=True).items)

        rows = fetch_complete_schedule_snapshot(client)
        stub_count = _ensure_schedule_worker_stubs(rows, synchronizer)
        synchronizer.sync_shifts(rows)
        if synchronizer.errors:
            raise WhenIWorkError(f'WIW schedule import produced errors: {synchronizer.errors[:5]}')

        remote_ids = {
            value
            for item in rows
            if (value := as_id(first(item, 'id', 'shift_id')))
        }
        local_ids = set(
            Shift.objects.exclude(wiw_shift_id__isnull=True)
            .exclude(wiw_shift_id='')
            .values_list('wiw_shift_id', flat=True)
        )
        missing = sorted(remote_ids - {str(value) for value in local_ids})
        if missing:
            raise WhenIWorkError(
                'WIW schedule reconciliation still has missing local shifts: '
                + ', '.join(missing[:20])
            )

        _reapply_schedule_worker_config()
        return {
            'status': 'success',
            'resource': 'shifts',
            'remote_count': len(remote_ids),
            'missing_local_count': 0,
            'historical_worker_stubs_created': stub_count,
            'counts': dict(synchronizer.counts),
        }
    finally:
        _release_wiw_reconciliation_lock(lock_token)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={'max_retries': 4})
def reconcile_when_i_work_full(self):
    """Daily complete WIW -> A+ reconciliation with a strict post-import proof."""
    if not settings.WIW_SYNC_ENABLED:
        return {'status': 'disabled'}
    lock_token = _acquire_wiw_reconciliation_lock()
    if not lock_token:
        return _retry_wiw_reconciliation_when_busy(self)

    try:
        from .wiw import WhenIWorkError
        from .wiw_migration import build_wiw_migration_report

        report = build_wiw_migration_report(apply_full_sync=True)
        if not report.get('cutover_ready'):
            incomplete = [
                name
                for name, row in report.get('resources', {}).items()
                if not row.get('complete')
            ]
            raise WhenIWorkError(
                'Full WIW reconciliation found incomplete resources: '
                + ', '.join(incomplete or ['unknown'])
            )
        _reapply_schedule_worker_config()
        return {
            'status': 'success',
            'cutover_ready': True,
            'resources': {
                name: {
                    'remote_count': row.get('remote_count', 0),
                    'local_count': row.get('local_count', 0),
                    'missing_local_count': row.get('missing_local_count', 0),
                }
                for name, row in report.get('resources', {}).items()
            },
        }
    finally:
        _release_wiw_reconciliation_lock(lock_token)


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
