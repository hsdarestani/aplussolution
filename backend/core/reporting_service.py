import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.core.mail import EmailMessage
from django.utils import timezone
from openpyxl import Workbook

from .models import AuditLog, Shift, TimeEntry, User, WorkerProfile
from .payroll_models import WorkerTimesheet
from .reporting_models import ReportDefinition, ReportRun, ReportSchedule
from .workplace_access import can_view_wage, has_capability, visible_locations, visible_workers


FIELD_CATALOG = {
    'shifts': {
        'id': ('ID', False), 'date': ('Datum', False), 'starts_at': ('Beginn', False), 'ends_at': ('Ende', False),
        'scheduled_minutes': ('Plan-Minuten', False), 'employee_number': ('Personalnummer', False),
        'employee_name': ('Mitarbeiter', False), 'client': ('Kunde', False), 'location': ('Einsatzort', False),
        'position': ('Position', False), 'status': ('Status', False), 'is_open': ('OpenShift', False),
        'break_minutes': ('Pause (Min.)', False), 'required_count': ('Bedarf', False),
        'hourly_rate': ('Stundenlohn', True), 'scheduled_cost': ('Geplante Kosten', True),
    },
    'shift_history': {
        'created_at': ('Zeitpunkt', False), 'action': ('Aktion', False), 'actor': ('Benutzer', False),
        'shift_id': ('Schicht-ID', False), 'metadata': ('Details', False),
    },
    'times': {
        'id': ('ID', False), 'date': ('Datum', False), 'clock_in': ('Einstempelung', False),
        'clock_out': ('Ausstempelung', False), 'worked_minutes': ('Arbeitsminuten', False),
        'employee_number': ('Personalnummer', False), 'employee_name': ('Mitarbeiter', False),
        'approved': ('Freigegeben', False), 'location': ('Einsatzort', False), 'position': ('Position', False),
        'edit_reason': ('Korrekturgrund', False), 'hourly_rate': ('Stundenlohn', True), 'actual_cost': ('Ist-Kosten', True),
    },
    'timesheets': {
        'period': ('Periode', False), 'period_start': ('Von', False), 'period_end': ('Bis', False),
        'employee_number': ('Personalnummer', False), 'employee_name': ('Mitarbeiter', False), 'status': ('Status', False),
        'gross_minutes': ('Brutto-Minuten', False), 'net_minutes': ('Netto-Minuten', False),
        'entry_count': ('Einträge', False), 'exception_count': ('Ausnahmen', False),
        'blocking_exception_count': ('Blockierende Ausnahmen', False), 'gross_estimate': ('Lohnschätzung', True),
    },
    'labor': {
        'employee_number': ('Personalnummer', False), 'employee_name': ('Mitarbeiter', False),
        'location': ('Einsatzort', False), 'scheduled_minutes': ('Plan-Minuten', False),
        'actual_minutes': ('Ist-Minuten', False), 'variance_minutes': ('Abweichung (Min.)', False),
        'scheduled_cost': ('Plan-Kosten', True), 'actual_cost': ('Ist-Kosten', True), 'cost_variance': ('Kostenabweichung', True),
    },
}

DEFAULT_COLUMNS = {
    'shifts': ['date', 'starts_at', 'ends_at', 'employee_name', 'client', 'location', 'position', 'status'],
    'shift_history': ['created_at', 'action', 'actor', 'shift_id', 'metadata'],
    'times': ['date', 'clock_in', 'clock_out', 'employee_name', 'worked_minutes', 'approved', 'location', 'position'],
    'timesheets': ['period', 'employee_name', 'status', 'gross_minutes', 'net_minutes', 'entry_count', 'exception_count'],
    'labor': ['employee_name', 'location', 'scheduled_minutes', 'actual_minutes', 'variance_minutes'],
}


def field_catalog(user, source):
    catalog = FIELD_CATALOG.get(source, {})
    wage = has_capability(user, 'wage.view')
    return [{'key': key, 'label': label, 'wage': wage_only} for key, (label, wage_only) in catalog.items() if wage or not wage_only]


def _date(value, fallback):
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError as exc:
        raise ValueError('Ungültiges Datumsformat.') from exc


def _bounds(filters):
    today = timezone.localdate()
    start = _date(filters.get('date_from'), today - timedelta(days=30))
    end = _date(filters.get('date_to'), today)
    if end < start:
        raise ValueError('Bis-Datum darf nicht vor dem Von-Datum liegen.')
    if (end - start).days > 730:
        raise ValueError('Berichtszeitraum darf maximal 730 Tage umfassen.')
    tz = timezone.get_current_timezone()
    return start, end, timezone.make_aware(datetime.combine(start, time.min), tz), timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)


def _filter_ids(qs, filters, *, shift_prefix=''):
    prefix = f'{shift_prefix}__' if shift_prefix else ''
    if filters.get('worker'):
        qs = qs.filter(**{f'{prefix}worker_id': filters['worker']})
    if filters.get('location'):
        qs = qs.filter(**{f'{prefix}location_id': filters['location']})
    if filters.get('position'):
        qs = qs.filter(**{f'{prefix}position_id': filters['position']})
    if filters.get('status') and not shift_prefix:
        qs = qs.filter(status=filters['status'])
    if filters.get('schedule'):
        qs = qs.filter(**{f'{prefix}location__schedule_groups__id': filters['schedule']})
    return qs.distinct()


def _money(value):
    return Decimal(value or 0).quantize(Decimal('0.01'))


def _shift_rows(user, filters):
    _, _, start_at, end_at = _bounds(filters)
    qs = Shift.objects.filter(location__in=visible_locations(user), starts_at__gte=start_at, starts_at__lt=end_at)
    qs = _filter_ids(qs, filters).select_related('worker__user', 'client', 'location', 'position').order_by('starts_at')
    rows = []
    for shift in qs[:20000]:
        minutes = max(0, int((shift.ends_at - shift.starts_at).total_seconds() // 60) - shift.break_minutes)
        worker = shift.worker
        rate = _money((worker.tariff_hourly_rate or 0) + (worker.extra_allowance or 0)) if worker and can_view_wage(user, worker) else None
        rows.append({
            'id': str(shift.id), 'date': shift.starts_at.date(), 'starts_at': shift.starts_at, 'ends_at': shift.ends_at,
            'scheduled_minutes': minutes, 'employee_number': worker.employee_number if worker else '',
            'employee_name': (worker.user.get_full_name() or worker.user.email) if worker else 'OpenShift',
            'client': shift.client.name, 'location': shift.location.name, 'position': shift.position.name,
            'status': shift.get_status_display(), 'is_open': bool(shift.is_open or not worker), 'break_minutes': shift.break_minutes,
            'required_count': shift.required_count, 'hourly_rate': rate,
            'scheduled_cost': _money(Decimal(minutes) / Decimal(60) * rate) if rate is not None else None,
        })
    return rows


def _time_rows(user, filters):
    _, _, start_at, end_at = _bounds(filters)
    qs = TimeEntry.objects.filter(worker__in=visible_workers(user), clock_in__gte=start_at, clock_in__lt=end_at)
    if filters.get('worker'):
        qs = qs.filter(worker_id=filters['worker'])
    if filters.get('approved') not in (None, ''):
        value = str(filters['approved']).lower() in {'1', 'true', 'yes'}
        qs = qs.filter(approved=value)
    if filters.get('location'):
        qs = qs.filter(shift__location_id=filters['location'])
    if filters.get('position'):
        qs = qs.filter(shift__position_id=filters['position'])
    if filters.get('schedule'):
        qs = qs.filter(shift__location__schedule_groups__id=filters['schedule'])
    qs = qs.select_related('worker__user', 'shift__location', 'shift__position').distinct().order_by('clock_in')
    rows = []
    for entry in qs[:20000]:
        worker = entry.worker
        rate = _money((worker.tariff_hourly_rate or 0) + (worker.extra_allowance or 0)) if can_view_wage(user, worker) else None
        rows.append({
            'id': str(entry.id), 'date': entry.clock_in.date(), 'clock_in': entry.clock_in, 'clock_out': entry.clock_out,
            'worked_minutes': entry.worked_minutes, 'employee_number': worker.employee_number,
            'employee_name': worker.user.get_full_name() or worker.user.email, 'approved': entry.approved,
            'location': entry.shift.location.name if entry.shift_id else '', 'position': entry.shift.position.name if entry.shift_id else '',
            'edit_reason': entry.edit_reason, 'hourly_rate': rate,
            'actual_cost': _money(Decimal(entry.worked_minutes) / Decimal(60) * rate) if rate is not None else None,
        })
    return rows


def _timesheet_rows(user, filters):
    start, end, _, _ = _bounds(filters)
    qs = WorkerTimesheet.objects.filter(worker__in=visible_workers(user), pay_period__ends_on__gte=start, pay_period__starts_on__lte=end)
    if filters.get('worker'):
        qs = qs.filter(worker_id=filters['worker'])
    if filters.get('status'):
        qs = qs.filter(status=filters['status'])
    qs = qs.select_related('worker__user', 'pay_period').order_by('-pay_period__starts_on', 'worker__employee_number')
    rows = []
    for sheet in qs[:20000]:
        wage = can_view_wage(user, sheet.worker)
        rows.append({
            'period': sheet.pay_period.name, 'period_start': sheet.pay_period.starts_on, 'period_end': sheet.pay_period.ends_on,
            'employee_number': sheet.worker.employee_number, 'employee_name': sheet.worker.user.get_full_name() or sheet.worker.user.email,
            'status': sheet.get_status_display(), 'gross_minutes': sheet.gross_minutes, 'net_minutes': sheet.net_minutes,
            'entry_count': sheet.entry_count, 'exception_count': sheet.exception_count,
            'blocking_exception_count': sheet.blocking_exception_count, 'gross_estimate': _money(sheet.gross_estimate) if wage else None,
        })
    return rows


def _history_rows(user, filters):
    start, end, start_at, end_at = _bounds(filters)
    shift_ids = set(Shift.objects.filter(location__in=visible_locations(user), starts_at__date__gte=start, starts_at__date__lte=end).values_list('id', flat=True))
    qs = AuditLog.objects.filter(created_at__gte=start_at, created_at__lt=end_at).filter(object_type='Shift')
    rows = []
    for item in qs.select_related('actor')[:20000]:
        try:
            object_id = str(item.object_id)
        except Exception:
            continue
        if object_id not in {str(x) for x in shift_ids}:
            continue
        rows.append({
            'created_at': item.created_at, 'action': item.action,
            'actor': (item.actor.get_full_name() or item.actor.email) if item.actor else 'System',
            'shift_id': object_id, 'metadata': json.dumps(item.metadata or {}, ensure_ascii=False, sort_keys=True),
        })
    return rows


def _labor_rows(user, filters):
    shifts = _shift_rows(user, filters)
    times = _time_rows(user, filters)
    bucket = defaultdict(lambda: {'scheduled_minutes': 0, 'actual_minutes': 0, 'scheduled_cost': Decimal('0'), 'actual_cost': Decimal('0')})
    names = {}
    for row in shifts:
        if not row['employee_number']:
            continue
        key = (row['employee_number'], row['location'])
        names[key] = row['employee_name']
        bucket[key]['scheduled_minutes'] += row['scheduled_minutes']
        if row['scheduled_cost'] is not None:
            bucket[key]['scheduled_cost'] += row['scheduled_cost']
    for row in times:
        key = (row['employee_number'], row['location'])
        names[key] = row['employee_name']
        bucket[key]['actual_minutes'] += row['worked_minutes']
        if row['actual_cost'] is not None:
            bucket[key]['actual_cost'] += row['actual_cost']
    rows = []
    for (number, location), totals in sorted(bucket.items()):
        wage = has_capability(user, 'wage.view')
        rows.append({
            'employee_number': number, 'employee_name': names.get((number, location), number), 'location': location,
            'scheduled_minutes': totals['scheduled_minutes'], 'actual_minutes': totals['actual_minutes'],
            'variance_minutes': totals['actual_minutes'] - totals['scheduled_minutes'],
            'scheduled_cost': _money(totals['scheduled_cost']) if wage else None,
            'actual_cost': _money(totals['actual_cost']) if wage else None,
            'cost_variance': _money(totals['actual_cost'] - totals['scheduled_cost']) if wage else None,
        })
    return rows


SOURCE_LOADERS = {
    'shifts': _shift_rows, 'shift_history': _history_rows, 'times': _time_rows,
    'timesheets': _timesheet_rows, 'labor': _labor_rows,
}


def _sort_rows(rows, sort):
    for rule in reversed(sort or []):
        field = rule.get('field') if isinstance(rule, dict) else str(rule)
        reverse = isinstance(rule, dict) and str(rule.get('direction', 'asc')).lower() == 'desc'
        if field:
            rows.sort(key=lambda row: (row.get(field) is None, str(row.get(field, ''))), reverse=reverse)
    return rows


def _aggregate(rows, group_by, aggregates):
    if not group_by and not aggregates:
        return rows, None
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(field) for field in group_by)].append(row)
    result = []
    for key, items in groups.items():
        row = {field: key[index] for index, field in enumerate(group_by)}
        for spec in aggregates:
            field = spec.get('field')
            op = spec.get('op')
            alias = spec.get('alias') or f'{op}_{field}'
            values = [item.get(field) for item in items if isinstance(item.get(field), (int, float, Decimal))]
            if op == 'count': row[alias] = len(items)
            elif op == 'sum': row[alias] = sum(values, 0)
            elif op == 'avg': row[alias] = (sum(values, 0) / len(values)) if values else 0
            elif op == 'min': row[alias] = min(values) if values else None
            elif op == 'max': row[alias] = max(values) if values else None
            else: raise ValueError(f'Nicht unterstützte Aggregation: {op}')
        result.append(row)
    return result, [*group_by, *[(item.get('alias') or f"{item.get('op')}_{item.get('field')}") for item in aggregates]]


def build_report(user, source, columns=None, filters=None, sort=None, group_by=None, aggregates=None, limit=None):
    if not has_capability(user, 'reports.view'):
        raise PermissionError('Keine Berechtigung für Berichte.')
    if source not in SOURCE_LOADERS:
        raise ValueError('Unbekannte Datenquelle.')
    filters = dict(filters or {})
    allowed = {item['key'] for item in field_catalog(user, source)}
    requested = list(columns or DEFAULT_COLUMNS[source])
    if any(field not in allowed for field in requested):
        raise PermissionError('Mindestens eine Spalte ist nicht freigegeben.')
    group_by = list(group_by or [])
    if any(field not in allowed for field in group_by):
        raise PermissionError('Gruppierung enthält eine nicht freigegebene Spalte.')
    aggregates = list(aggregates or [])
    if any(item.get('field') not in allowed for item in aggregates):
        raise PermissionError('Aggregation enthält eine nicht freigegebene Spalte.')
    rows = SOURCE_LOADERS[source](user, filters)
    rows = _sort_rows(rows, sort or [])
    rows, aggregate_columns = _aggregate(rows, group_by, aggregates)
    if aggregate_columns is not None:
        requested = aggregate_columns
    if limit:
        rows = rows[:int(limit)]
    labels = {key: FIELD_CATALOG[source].get(key, (key, False))[0] for key in requested}
    for item in aggregates:
        alias = item.get('alias') or f"{item.get('op')}_{item.get('field')}"
        labels[alias] = item.get('label') or alias
    return {'source': source, 'columns': [{'key': key, 'label': labels.get(key, key)} for key in requested], 'rows': [{key: row.get(key) for key in requested} for row in rows], 'total_rows': len(rows), 'filters': filters}


def _cell(value):
    if value is None: return ''
    if isinstance(value, bool): return 'Ja' if value else 'Nein'
    if isinstance(value, Decimal): return f'{value:.2f}'
    if hasattr(value, 'astimezone'): return value.astimezone().strftime('%d.%m.%Y %H:%M')
    if hasattr(value, 'strftime'): return value.strftime('%d.%m.%Y')
    return str(value)


def export_bytes(result, file_format='csv'):
    headers = [item['label'] for item in result['columns']]
    keys = [item['key'] for item in result['columns']]
    if file_format == 'csv':
        stream = io.StringIO()
        writer = csv.writer(stream, delimiter=';', lineterminator='\n')
        writer.writerow(headers)
        for row in result['rows']:
            writer.writerow([_cell(row.get(key)) for key in keys])
        data = b'\xef\xbb\xbf' + stream.getvalue().encode('utf-8')
        return data, 'text/csv; charset=utf-8'
    if file_format == 'xlsx':
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'Bericht'
        sheet.append(headers)
        for row in result['rows']:
            sheet.append([_cell(row.get(key)) for key in keys])
        stream = io.BytesIO()
        workbook.save(stream)
        return stream.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    raise ValueError('Exportformat muss csv oder xlsx sein.')


def execute_definition(definition, user, file_format='csv', filters_override=None, trigger=ReportRun.Trigger.MANUAL, schedule=None):
    filters = {**(definition.filters or {}), **(filters_override or {})}
    run = ReportRun.objects.create(
        report=definition, schedule=schedule, requested_by=user, trigger=trigger, file_format=file_format,
        filters_snapshot=filters,
    )
    try:
        result = build_report(user, definition.data_source, definition.columns, filters, definition.sort, definition.group_by, definition.aggregates)
        data, content_type = export_bytes(result, file_format)
        run.status = ReportRun.Status.SUCCESS
        run.row_count = len(result['rows'])
        run.checksum = hashlib.sha256(data).hexdigest()
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'row_count', 'checksum', 'completed_at', 'updated_at'])
        definition.last_run_at = run.completed_at
        definition.save(update_fields=['last_run_at', 'updated_at'])
        return run, data, content_type
    except Exception as exc:
        run.status = ReportRun.Status.FAILED
        run.error = str(exc)
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'error', 'completed_at', 'updated_at'])
        raise


def _next_run(schedule, now=None):
    from zoneinfo import ZoneInfo
    now = now or timezone.now()
    zone = ZoneInfo(schedule.timezone)
    local = now.astimezone(zone)
    candidate = local.replace(hour=min(schedule.local_hour, 23), minute=0, second=0, microsecond=0)
    if schedule.frequency == ReportSchedule.Frequency.DAILY:
        if candidate <= local: candidate += timedelta(days=1)
    elif schedule.frequency == ReportSchedule.Frequency.WEEKLY:
        days = (min(schedule.weekday, 6) - candidate.weekday()) % 7
        candidate += timedelta(days=days)
        if candidate <= local: candidate += timedelta(days=7)
    else:
        day = min(max(schedule.day_of_month, 1), 28)
        candidate = candidate.replace(day=day)
        if candidate <= local:
            month = candidate.month + 1
            year = candidate.year + (month > 12)
            month = 1 if month > 12 else month
            candidate = candidate.replace(year=year, month=month, day=day)
    return candidate.astimezone(timezone.get_current_timezone())


def send_scheduled_report(schedule):
    owner = schedule.created_by
    run, data, content_type = execute_definition(
        schedule.report, owner, schedule.file_format, trigger=ReportRun.Trigger.SCHEDULED, schedule=schedule,
    )
    extension = schedule.file_format
    message = EmailMessage(
        subject=f'A+ Workforce Bericht: {schedule.report.name}',
        body=f'Der geplante Bericht „{schedule.report.name}“ ist angehängt. Zeilen: {run.row_count}.',
        to=list(schedule.recipients or []),
    )
    message.attach(f'{schedule.report.name}.{extension}', data, content_type.split(';')[0])
    message.send(fail_silently=False)
    now = timezone.now()
    schedule.last_run_at = now
    schedule.next_run_at = _next_run(schedule, now)
    schedule.save(update_fields=['last_run_at', 'next_run_at', 'updated_at'])
    return run
