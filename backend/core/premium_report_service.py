from __future__ import annotations

from .models import AuditLog, Shift, TimeEntry, TimeOffRequest, WorkerProfile
from .premium_services import labor_forecast
from .shift_slots import ShiftSlot


def _apply_filters(rows, filters):
    filters = filters or {}
    for key, expected in filters.items():
        if key == 'location_id':
            continue
        if expected is None or expected == '' or expected == []:
            continue
        if isinstance(expected, list):
            allowed = {str(value).lower() for value in expected}
            rows = [row for row in rows if str(row.get(key, '')).lower() in allowed]
        else:
            expected_text = str(expected).lower()
            rows = [row for row in rows if expected_text in str(row.get(key, '')).lower()]
    return rows


def _apply_sorting(rows, sorting):
    for item in reversed(sorting or []):
        if isinstance(item, dict):
            field = item.get('field')
            descending = item.get('direction') == 'desc'
        else:
            raw = str(item)
            field = raw.lstrip('-')
            descending = raw.startswith('-')
        if not field:
            continue
        rows.sort(
            key=lambda row: (row.get(field) is None, str(row.get(field, '')).lower()),
            reverse=descending,
        )
    return rows


def run_report(definition, start, end):
    rows = []

    if definition.kind == 'shifts':
        queryset = Shift.objects.select_related('location', 'position').filter(
            starts_at__gte=start,
            starts_at__lte=end,
        )
        for shift in queryset:
            rows.append({
                'shift_id': str(shift.id),
                'start': shift.starts_at.isoformat(),
                'end': shift.ends_at.isoformat(),
                'location': shift.location.name,
                'position': shift.position.name,
                'status': shift.status,
                'required_count': shift.required_count,
                'claimed_count': shift.slots.filter(status=ShiftSlot.Status.CLAIMED).count(),
            })
    elif definition.kind == 'times':
        queryset = TimeEntry.objects.select_related('worker__user', 'shift__location').filter(
            clock_in__gte=start,
            clock_in__lte=end,
        )
        for entry in queryset:
            rows.append({
                'time_id': str(entry.id),
                'worker': entry.worker.user.get_full_name() or entry.worker.user.email,
                'employee_number': entry.worker.employee_number,
                'clock_in': entry.clock_in.isoformat(),
                'clock_out': entry.clock_out.isoformat() if entry.clock_out else None,
                'worked_minutes': entry.worked_minutes,
                'approved': entry.approved,
                'location': entry.shift.location.name if entry.shift else None,
            })
    elif definition.kind == 'shift_history':
        queryset = AuditLog.objects.select_related('actor').filter(
            created_at__gte=start,
            created_at__lte=end,
            object_type__icontains='shift',
        )
        for log in queryset:
            rows.append({
                'timestamp': log.created_at.isoformat(),
                'actor': log.actor.email if log.actor else None,
                'action': log.action,
                'shift_id': log.object_id,
                'metadata': log.metadata,
            })
    elif definition.kind == 'users':
        for worker in WorkerProfile.objects.select_related('user'):
            rows.append({
                'worker_id': str(worker.id),
                'employee_number': worker.employee_number,
                'name': worker.user.get_full_name(),
                'email': worker.user.email,
                'employment_type': worker.employment_type,
                'monthly_hours': str(worker.monthly_hours or ''),
                'skills': worker.skills,
                'active': worker.active,
            })
    elif definition.kind == 'time_off':
        queryset = TimeOffRequest.objects.select_related('worker__user').filter(
            starts_on__lte=end.date(),
            ends_on__gte=start.date(),
        )
        for request in queryset:
            rows.append({
                'request_id': str(request.id),
                'worker': request.worker.user.get_full_name() or request.worker.user.email,
                'start': request.starts_on.isoformat(),
                'end': request.ends_on.isoformat(),
                'status': request.status,
                'reason': request.reason,
            })
    else:
        rows = labor_forecast(
            start.date(),
            end.date(),
            (definition.filters or {}).get('location_id'),
        )

    rows = _apply_filters(rows, definition.filters)
    rows = _apply_sorting(rows, definition.sorting)
    columns = definition.columns or (list(rows[0].keys()) if rows else [])
    projected = [{column: row.get(column) for column in columns} for row in rows]
    return columns, projected
