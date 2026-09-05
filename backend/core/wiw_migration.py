from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone

from .models import Availability, IntegrationSyncRun, Location, Position, Shift, TimeEntry, TimeOffRequest, User, WorkerProfile
from .wiw import WhenIWorkClient, WhenIWorkError
from .wiw_sync import WhenIWorkSynchronizer, as_date, as_datetime, as_id, first, synthetic_email


DYNAMIC_RESOURCES = {'shifts', 'times', 'availabilities', 'requests'}
HISTORY_START = date(2000, 1, 1)
HISTORY_END = date(2100, 1, 1)
FETCH_LIMIT = 1000
MAX_DYNAMIC_WINDOW_DAYS = 366


def _id_set(items, *keys):
    values = set()
    for item in items:
        value = as_id(first(item, *keys))
        if value:
            values.add(value)
    return values


def _utc_iso(value):
    return value.astimezone(datetime_timezone.utc).isoformat()


def _range_param(value: date):
    return datetime(value.year, value.month, value.day, tzinfo=datetime_timezone.utc).isoformat().replace('+00:00', 'Z')


def _item_identity(resource, item):
    id_keys = {
        'users': ('id', 'user_id'),
        'positions': ('id', 'position_id'),
        'locations': ('id', 'location_id'),
        'sites': ('id', 'site_id'),
        'shifts': ('id', 'shift_id'),
        'times': ('id', 'time_id'),
    }
    if resource in id_keys:
        return as_id(first(item, *id_keys[resource]))
    if resource == 'availabilities':
        return _availability_remote_key(item)
    if resource == 'requests':
        return _request_remote_key(item)
    return None


def _dedupe(resource, rows):
    result = []
    seen = set()
    for item in rows:
        key = _item_identity(resource, item)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(item)
    return result


def _fetch_static_resource(client, resource):
    rows = client.collection(resource, params={'limit': FETCH_LIMIT}, optional=False).items
    if len(rows) >= FETCH_LIMIT:
        raise WhenIWorkError(
            f'WIW resource {resource} returned {len(rows)} rows at the safety limit; '
            'a complete import cannot be proven automatically.'
        )
    return rows


def _dynamic_params(resource, start: date, end: date):
    params = {'start': _range_param(start), 'end': _range_param(end), 'limit': FETCH_LIMIT}
    if resource == 'shifts':
        # A normal WIW shifts request can omit OpenShifts or shifts outside the
        # caller's default location scope. Full reconciliation must explicitly
        # request both or it could incorrectly prove a partial snapshot complete.
        params.update({
            'include_open': 'true',
            'include_allopen': 'true',
            'all_locations': 'true',
        })
    return params


def _fetch_dynamic_range(client, resource, start: date, end: date, depth=0):
    """Fetch a complete range without trusting WIW to honor very broad date windows.

    WIW can return an empty response for an excessively broad range even when the
    resource contains current rows. Split proactively into at-most-one-year windows,
    then split further on API errors or when a window reaches the row safety cap.
    """
    if end <= start:
        return []

    span_days = (end - start).days
    if span_days > MAX_DYNAMIC_WINDOW_DAYS:
        midpoint = start + timedelta(days=max(1, span_days // 2))
        return _dedupe(
            resource,
            _fetch_dynamic_range(client, resource, start, midpoint, depth + 1)
            + _fetch_dynamic_range(client, resource, midpoint, end, depth + 1),
        )

    params = _dynamic_params(resource, start, end)
    try:
        rows = client.collection(resource, params=params, optional=False).items
    except WhenIWorkError:
        if span_days <= 1 or depth >= 24:
            raise
        midpoint = start + timedelta(days=max(1, span_days // 2))
        return _dedupe(
            resource,
            _fetch_dynamic_range(client, resource, start, midpoint, depth + 1)
            + _fetch_dynamic_range(client, resource, midpoint, end, depth + 1),
        )

    if len(rows) < FETCH_LIMIT:
        return rows
    if span_days <= 1 or depth >= 24:
        raise WhenIWorkError(
            f'WIW resource {resource} still reaches the {FETCH_LIMIT}-row safety limit for {start}–{end}; '
            'the final migration refuses to claim completeness.'
        )
    midpoint = start + timedelta(days=max(1, span_days // 2))
    return _dedupe(
        resource,
        _fetch_dynamic_range(client, resource, start, midpoint, depth + 1)
        + _fetch_dynamic_range(client, resource, midpoint, end, depth + 1),
    )


def _assert_dynamic_probe_is_in_snapshot(client, resource, rows):
    """Guard against a silent-empty range response using WIW's default/current view."""
    probe_params = {'limit': 50}
    if resource == 'shifts':
        probe_params.update({
            'include_open': 'true',
            'include_allopen': 'true',
            'all_locations': 'true',
        })
    probe = client.collection(resource, params=probe_params, optional=False).items
    probe_keys = {key for item in probe if (key := _item_identity(resource, item))}
    snapshot_keys = {key for item in rows if (key := _item_identity(resource, item))}
    missing = sorted(probe_keys - snapshot_keys)
    if missing:
        raise WhenIWorkError(
            f'WIW resource {resource} returned current/default rows that were absent from the bounded history fetch: '
            + ', '.join(missing[:20])
        )


def fetch_complete_wiw_snapshot(client):
    snapshot = {}
    errors = {}
    for resource in ('users', 'positions', 'locations', 'sites', 'shifts', 'times', 'availabilities', 'requests'):
        try:
            if resource in DYNAMIC_RESOURCES:
                rows = _fetch_dynamic_range(client, resource, HISTORY_START, HISTORY_END)
                _assert_dynamic_probe_is_in_snapshot(client, resource, rows)
                snapshot[resource] = rows
            else:
                snapshot[resource] = _fetch_static_resource(client, resource)
        except WhenIWorkError as exc:
            snapshot[resource] = []
            errors[resource] = str(exc)
    return snapshot, errors


def _ensure_historical_time_workers(snapshot, synchronizer):
    """Create inactive archival workers for time rows whose users are no longer returned by WIW /users."""
    time_user_ids = {
        user_id
        for item in snapshot.get('times', [])
        if (user_id := as_id(first(item, 'user_id', 'user')))
    }
    known = set(synchronizer.workers)
    known.update(
        str(value)
        for value in WorkerProfile.objects.exclude(wiw_user_id__isnull=True)
        .exclude(wiw_user_id='')
        .values_list('wiw_user_id', flat=True)
    )
    missing = sorted(time_user_ids - known)
    for wiw_user_id in missing:
        worker = WorkerProfile.objects.filter(wiw_user_id=wiw_user_id).select_related('user').first()
        if worker:
            synchronizer.workers[wiw_user_id] = worker
            continue

        email = synthetic_email(wiw_user_id)
        user = User.objects.filter(wiw_id=wiw_user_id).first() or User.objects.filter(email=email).first()
        user_created = not bool(user)
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
            'source': 'wiw_times',
        }
        user.wiw_synced_at = timezone.now()
        if user_created:
            user.is_active = False
            user.is_onboarded = False
        user.save()

        worker, worker_created = WorkerProfile.objects.get_or_create(
            user=user,
            defaults={
                'employee_number': f'WIW-HIST-{wiw_user_id}'[:50],
                'active': False,
                'wiw_user_id': wiw_user_id,
                'wiw_payload': {'historical_archive_stub': True, 'source': 'wiw_times'},
                'wiw_synced_at': timezone.now(),
            },
        )
        if not worker.wiw_user_id:
            worker.wiw_user_id = wiw_user_id
            worker.save(update_fields=['wiw_user_id', 'updated_at'])
        synchronizer.workers[wiw_user_id] = worker
        synchronizer.counts['historical_users_created' if user_created else 'historical_users_reused'] += 1
        synchronizer.counts['historical_workers_created' if worker_created else 'historical_workers_reused'] += 1
    return len(missing)


def _run_final_import(snapshot, *, client, actor=None):
    """Import the already-fetched complete snapshot without relying on the legacy range-less sync."""
    synchronizer = WhenIWorkSynchronizer(client=client, triggered_by=actor)
    with transaction.atomic():
        run = IntegrationSyncRun.objects.create(
            provider='wiw',
            mode='final_full',
            status=IntegrationSyncRun.Status.RUNNING,
            triggered_by=actor,
        )
        synchronizer.sync_users(snapshot['users'])
        _ensure_historical_time_workers(snapshot, synchronizer)
        synchronizer.sync_positions(snapshot['positions'])
        synchronizer.sync_locations(snapshot['locations'])
        synchronizer.sync_sites(snapshot['sites'])
        synchronizer.sync_shifts(snapshot['shifts'])
        synchronizer.sync_times(snapshot['times'])
        synchronizer.sync_availabilities(snapshot['availabilities'])
        synchronizer.sync_requests(snapshot['requests'])
        run.finished_at = timezone.now()
        run.counts = dict(synchronizer.counts)
        run.errors = synchronizer.errors
        run.status = IntegrationSyncRun.Status.PARTIAL if synchronizer.errors else IntegrationSyncRun.Status.SUCCESS
        run.save(update_fields=['status', 'finished_at', 'counts', 'errors', 'updated_at'])
    return run


def _availability_remote_key(item):
    worker = as_id(first(item, 'user_id', 'user'))
    start = as_datetime(first(item, 'start_time', 'start', 'starts_at'))
    end = as_datetime(first(item, 'end_time', 'end', 'ends_at'))
    if not worker or not start or not end:
        return None
    return f'{worker}|{_utc_iso(start)}|{_utc_iso(end)}'


def _request_remote_key(item):
    worker = as_id(first(item, 'user_id', 'user'))
    start = as_date(first(item, 'start_date', 'start_time', 'start'))
    end = as_date(first(item, 'end_date', 'end_time', 'end'))
    if not worker or not start or not end:
        return None
    return f'{worker}|{start.isoformat()}|{end.isoformat()}'


def _availability_local_keys():
    rows = Availability.objects.exclude(worker__wiw_user_id__isnull=True).exclude(worker__wiw_user_id='').select_related('worker')
    return {f'{row.worker.wiw_user_id}|{_utc_iso(row.starts_at)}|{_utc_iso(row.ends_at)}' for row in rows}


def _request_local_keys():
    rows = TimeOffRequest.objects.exclude(worker__wiw_user_id__isnull=True).exclude(worker__wiw_user_id='').select_related('worker')
    return {f'{row.worker.wiw_user_id}|{row.starts_on.isoformat()}|{row.ends_on.isoformat()}' for row in rows}


def _comparison(remote: set[str], local: set[str], *, error=''):
    missing = sorted(remote - local)
    extra = sorted(local - remote)
    return {
        'remote_count': len(remote),
        'local_count': len(local),
        'matched_count': len(remote & local),
        'missing_local_count': len(missing),
        'missing_local_sample': missing[:50],
        'extra_local_count': len(extra),
        'error': error,
        'complete': not error and not missing,
    }


def build_wiw_migration_report(*, apply_full_sync=False, actor=None, client=None):
    """Fetch the complete WIW snapshot, optionally import it once, then prove local reconciliation."""
    client = client or WhenIWorkClient()
    remote, errors = fetch_complete_wiw_snapshot(client)
    sync = None
    if apply_full_sync and not errors:
        run = _run_final_import(remote, client=client, actor=actor)
        sync = {
            'id': str(run.id),
            'status': run.status,
            'counts': run.counts,
            'errors': run.errors,
        }
    elif apply_full_sync and errors:
        sync = {'status': 'not_started', 'errors': errors}

    local_sets = {
        'users': set(User.objects.exclude(wiw_id__isnull=True).exclude(wiw_id='').values_list('wiw_id', flat=True)),
        'positions': set(Position.objects.exclude(wiw_position_id__isnull=True).exclude(wiw_position_id='').values_list('wiw_position_id', flat=True)),
        'locations': set(Location.objects.exclude(wiw_location_id__isnull=True).exclude(wiw_location_id='').values_list('wiw_location_id', flat=True)),
        'sites': set(Location.objects.exclude(wiw_site_id__isnull=True).exclude(wiw_site_id='').values_list('wiw_site_id', flat=True)),
        'shifts': set(Shift.objects.exclude(wiw_shift_id__isnull=True).exclude(wiw_shift_id='').values_list('wiw_shift_id', flat=True)),
        'times': set(TimeEntry.objects.exclude(wiw_time_id__isnull=True).exclude(wiw_time_id='').values_list('wiw_time_id', flat=True)),
        'availabilities': _availability_local_keys(),
        'requests': _request_local_keys(),
    }
    remote_sets = {
        'users': _id_set(remote['users'], 'id', 'user_id'),
        'positions': _id_set(remote['positions'], 'id', 'position_id'),
        'locations': _id_set(remote['locations'], 'id', 'location_id'),
        'sites': _id_set(remote['sites'], 'id', 'site_id'),
        'shifts': _id_set(remote['shifts'], 'id', 'shift_id'),
        'times': _id_set(remote['times'], 'id', 'time_id'),
        'availabilities': {key for item in remote['availabilities'] if (key := _availability_remote_key(item))},
        'requests': {key for item in remote['requests'] if (key := _request_remote_key(item))},
    }

    resources = {
        name: _comparison(remote_sets[name], local_sets[name], error=errors.get(name, ''))
        for name in remote_sets
    }
    complete = all(item['complete'] for item in resources.values())
    return {
        'source': 'when_i_work',
        'target': 'aplus_workforce',
        'history_window': {'start': HISTORY_START.isoformat(), 'end': HISTORY_END.isoformat()},
        'apply_full_sync': apply_full_sync,
        'sync': sync,
        'resources': resources,
        'complete': complete,
        'cutover_ready': complete,
        'note': (
            'A+ Workforce bleibt nach dem Import die einzige operative Datenquelle. '
            'WIW-IDs und Rohdaten bleiben ausschließlich für Audit/Traceability erhalten.'
        ),
    }
