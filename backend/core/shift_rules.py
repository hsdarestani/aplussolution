from __future__ import annotations

from datetime import datetime


SCHEDULE_GROUPS = {
    'service': 'Service',
    'front_office': 'Front Office',
    'housekeeping': 'Housekeeping',
}


def automatic_break_minutes(starts_at: datetime | None, ends_at: datetime | None) -> int:
    """Return the A+ mandatory automatic break for a native shift.

    Rules requested by operations:
    < 6h = 0, >= 6h = 30, >= 9h = 45, >= 11h = 60 minutes.
    """
    if not starts_at or not ends_at or ends_at <= starts_at:
        return 0
    hours = (ends_at - starts_at).total_seconds() / 3600
    if hours >= 11:
        return 60
    if hours >= 9:
        return 45
    if hours >= 6:
        return 30
    return 0


def normalized_groups(value) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    valid = set(SCHEDULE_GROUPS)
    result: list[str] = []
    for item in value:
        key = str(item or '').strip().lower().replace('-', '_').replace(' ', '_')
        if key in valid and key not in result:
            result.append(key)
    return result


def schedule_groups_for_position_name(value) -> list[str]:
    """Map an existing A+ position to its Zeitplan group.

    This is directory/system metadata logic, not parsing of the user's AI prompt.
    It is used as a safe fallback for older/native-created shifts that do not yet
    persist ``schedule_groups`` themselves.
    """
    name = str(value or '').strip().casefold().replace('-', ' ')
    compact = ' '.join(name.split())
    if any(token in compact for token in ('front office', 'rezeption', 'reception')):
        return ['front_office']
    if 'housekeeping' in compact or 'house keeping' in compact:
        return ['housekeeping']
    if any(token in compact for token in ('service', 'bar')):
        return ['service']
    return []


def shift_visible_to_worker(shift, worker) -> bool:
    """Apply per-worker OpenShift client and Zeitplan visibility.

    A shift with an explicit Zeitplan group is visible only to workers who are
    explicitly assigned to at least one matching group. If an older/native-created
    shift has no persisted group, infer it from the already-resolved Position so a
    Front Office OpenShift cannot fan out to every employee.
    """
    allowed_clients = {str(value) for value in (worker.open_shift_client_ids or []) if value}
    if allowed_clients and str(shift.client_id) not in allowed_clients:
        return False
    worker_groups = set(normalized_groups(worker.schedule_groups))
    shift_groups = set(normalized_groups(shift.schedule_groups))
    if not shift_groups:
        shift_groups = set(schedule_groups_for_position_name(getattr(getattr(shift, 'position', None), 'name', '')))
    if shift_groups and not worker_groups.intersection(shift_groups):
        return False
    return True
