from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone

from .models import Availability, IntegrationSyncRun, Location, Position, Shift, TimeEntry, TimeOffRequest, User
from .wiw import WhenIWorkClient, WhenIWorkError
from .wiw_sync import WhenIWorkSynchronizer, as_date, as_datetime, as_id, first


DYNAMIC_RESOURCES = {'shifts', 'times', 'availabilities', 'requests'}
HISTORY_START = date(2000, 1, 1)
HISTORY_END = date(2100, 1, 1)
FETCH_LIMIT = 1000


def _id_set(items, *keys):
    values = set()
    for item in items:
        value = as_id(first(item, *keys))
        if value:
            values.add(value)
    return values


def _utc_iso(value):
    return value.astimezone(datetime_timezone.utc).isoformat()


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


def _fetch_dynamic_range(client, resource, start: date, end: date, depth=0):
    """Fetch a complete date range, splitting when a response reaches the result cap or rejects a broad range."""
    if end <= start:
        return []
    params = {'start': start.isoformat(), 'end': end.isoformat(), 'limit': FETCH_LIMIT}
    try:
        rows = client.collection(resource, params=params, optional=False).items
    except WhenIWorkError:
        if (end - start).days <= 1 or depth >= 20:
            raise
        midpoint = start + timedelta(days=max(1, (end - start).days // 2))
        return _dedupe(
            resource,
            _fetch_dynamic_range(client, resource, start, midpoint, depth + 1)
            + _fetch_dynamic_range(client, resource, midpoint, end, depth + 1),
        )

    if len(rows) < FETCH_LIMIT:
        return rows
    if (end - start).days <= 1 or depth >= 20:
        raise WhenIWorkError(
            f'WIW resource {resource} still reaches the {FETCH_LIMIT}-row safety limit for {start}–{end}; '
            'the final migration refuses to claim completeness.'
        )
    midpoint = start + timedelta(days=max(1, (end - start).days // 2))
    return _dedupe(
        resource,
        _fetch_dynamic_range(client, resource, start, midpoint, depth + 1)
        + _fetch_dynamic_range(client, resource, midpoint, end, depth + 1),
    )


def fetch_complete_wiw_snapshot(client):
    snapshot = {}
    errors = {}
    for resource in ('users', 'positions', 'locations', 'sites', 'shifts', 'times', 'availabilities', 'requests'):
        try:
            if resource in DYNAMIC_RESOURCES:
                snapshot[resource] = _fetch_dynamic_range(client, resource, HISTORY_START, HISTORY_END)
            else:
                snapshot[resource] = _fetch_static_resource(client, resource)
        except WhenIWorkError as exc:
            snapshot[resource] = []
            errors[resource] = str(exc)
    return snapshot, errors


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
