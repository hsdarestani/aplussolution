from __future__ import annotations

from typing import Callable

from .models import Availability, Location, Position, Shift, TimeEntry, TimeOffRequest, User, WorkerProfile
from .wiw import WhenIWorkClient, WhenIWorkError
from .wiw_sync import WhenIWorkSynchronizer, as_date, as_datetime, as_id, first


def _id_set(items, *keys):
    values = set()
    for item in items:
        value = as_id(first(item, *keys))
        if value:
            values.add(value)
    return values


def _availability_remote_key(item):
    worker = as_id(first(item, 'user_id', 'user'))
    start = as_datetime(first(item, 'start_time', 'start', 'starts_at'))
    end = as_datetime(first(item, 'end_time', 'end', 'ends_at'))
    if not worker or not start or not end:
        return None
    return f'{worker}|{start.isoformat()}|{end.isoformat()}'


def _request_remote_key(item):
    worker = as_id(first(item, 'user_id', 'user'))
    start = as_date(first(item, 'start_date', 'start_time', 'start'))
    end = as_date(first(item, 'end_date', 'end_time', 'end'))
    if not worker or not start or not end:
        return None
    return f'{worker}|{start.isoformat()}|{end.isoformat()}'


def _availability_local_keys():
    rows = Availability.objects.exclude(worker__wiw_user_id__isnull=True).exclude(worker__wiw_user_id='').select_related('worker')
    return {f'{row.worker.wiw_user_id}|{row.starts_at.isoformat()}|{row.ends_at.isoformat()}' for row in rows}


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
    """Import WIW once (optional) and compare every migrated resource with local A+ data."""
    client = client or WhenIWorkClient()
    sync = None
    if apply_full_sync:
        run = WhenIWorkSynchronizer(client=client, triggered_by=actor).sync(mode='full')
        sync = {
            'id': str(run.id),
            'status': run.status,
            'counts': run.counts,
            'errors': run.errors,
        }

    remote = {}
    errors = {}
    for resource in ('users', 'positions', 'locations', 'sites', 'shifts', 'times', 'availabilities', 'requests'):
        try:
            remote[resource] = client.collection(resource, optional=False).items
        except WhenIWorkError as exc:
            remote[resource] = []
            errors[resource] = str(exc)

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
