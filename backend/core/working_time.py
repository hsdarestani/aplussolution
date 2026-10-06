import csv
import io
import json
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    PayrollStatement,
    User,
    WorkerProfile,
    WorkingTimeAccountRecord,
    WorkingTimeSetting,
    WorkingTimeSyncLog,
)
from .wiw import WhenIWorkClient, WhenIWorkError

TWO = Decimal('0.01')


def dec(value: Any, default='0') -> Decimal:
    try:
        return Decimal(str(value).replace(',', '.')).quantize(TWO, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal(default).quantize(TWO)


def month_start(value: str | date) -> date:
    if isinstance(value, date):
        return value.replace(day=1)
    return datetime.strptime(str(value)[:7], '%Y-%m').date()


def iter_months(start: date, end: date):
    current = start.replace(day=1)
    final = end.replace(day=1)
    while current <= final:
        yield current
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)


def next_month(value: date) -> date:
    return (value.replace(day=28) + timedelta(days=4)).replace(day=1)


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        parsed = None
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%m/%d/%Y %H:%M:%S'):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed.astimezone(timezone.get_current_timezone())


def first_value(row: dict, keys: tuple[str, ...], default=None):
    for key in keys:
        if key in row and row[key] not in (None, ''):
            return row[key]
    return default


def duration_to_hours(value: Any) -> Decimal | None:
    if value in (None, ''):
        return None
    if isinstance(value, str) and ':' in value:
        parts = [dec(item) for item in value.split(':')]
        result = (parts[0] if parts else Decimal('0'))
        if len(parts) > 1:
            result += parts[1] / Decimal('60')
        if len(parts) > 2:
            result += parts[2] / Decimal('3600')
        return result.quantize(TWO)
    try:
        number = Decimal(str(value))
    except Exception:
        return None
    if number < 0:
        return None
    if number > 1440:
        return (number / Decimal('3600')).quantize(TWO)
    if number > 24:
        return (number / Decimal('60')).quantize(TWO)
    return number.quantize(TWO)


def unpaid_break_minutes(entry: dict) -> Decimal:
    direct_hours = first_value(entry, ('unpaid_break_hours', 'break_hours'))
    if direct_hours not in (None, ''):
        return max(Decimal('0'), dec(direct_hours) * Decimal('60'))
    direct = first_value(entry, ('unpaid_break_minutes', 'break_minutes', 'break_time'), 0)
    if direct not in (None, ''):
        number = max(Decimal('0'), dec(direct))
        if number > 1440:
            number /= Decimal('60')
        if number:
            return number
    total = Decimal('0')
    for key in ('shiftbreaks', 'shift_breaks', 'shiftBreaks', 'breaks'):
        breaks = entry.get(key)
        if not isinstance(breaks, list):
            continue
        for item in breaks:
            if not isinstance(item, dict):
                continue
            paid = bool(item.get('paid', int(item.get('type') or 2) == 1))
            if paid:
                continue
            hours = first_value(item, ('duration_hours', 'hours'))
            if hours not in (None, ''):
                total += max(Decimal('0'), dec(hours) * Decimal('60'))
                continue
            length = max(Decimal('0'), dec(first_value(item, ('length', 'minutes', 'duration'), 0)))
            total += length / Decimal('60') if length > 1440 else length
    return total.quantize(TWO)


def entry_hours(entry: dict, source='wiw_times', fallback_break_minutes=0) -> tuple[Decimal, datetime | None, datetime | None]:
    start = parse_dt(first_value(entry, ('start_time', 'startTime', 'clock_in', 'clockin_time', 'clock_in_time', 'start', 'time_in')))
    end = parse_dt(first_value(entry, ('end_time', 'endTime', 'clock_out', 'clockout_time', 'clock_out_time', 'end', 'time_out')))
    if not start:
        return Decimal('0.00'), None, end
    if source != 'wiw_shifts':
        supplied = duration_to_hours(first_value(entry, ('length', 'worked_hours', 'total_hours', 'duration_hours', 'hours')))
        if supplied is not None and supplied > 0:
            return supplied, start, end
    if not end or end <= start:
        return Decimal('0.00'), start, end
    hours = Decimal(str((end - start).total_seconds())) / Decimal('3600')
    break_minutes = dec(fallback_break_minutes) if source == 'wiw_shifts' else unpaid_break_minutes(entry)
    return max(Decimal('0'), hours - break_minutes / Decimal('60')).quantize(TWO), start, end


def unwrap_entries(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ('times', 'entries', 'time_entries', 'items', 'results', 'records'):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload.get('data'), (dict, list)):
        return unwrap_entries(payload['data'])
    return []


def _time_query_candidates(start: date, end: date):
    start_dt = timezone.make_aware(datetime.combine(start, datetime.min.time()), timezone.get_current_timezone())
    end_dt = timezone.make_aware(datetime.combine(end, datetime.min.time()), timezone.get_current_timezone())
    utc = timezone.get_fixed_timezone(0)
    return [
        {'start': start_dt.astimezone(utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'end': end_dt.astimezone(utc).strftime('%Y-%m-%dT%H:%M:%SZ')},
        {'start': start_dt.isoformat(), 'end': end_dt.isoformat()},
        {'start': start_dt.strftime('%Y-%m-%dT%H:%M:%S'), 'end': end_dt.strftime('%Y-%m-%dT%H:%M:%S')},
        {'start': start.isoformat(), 'end': end.isoformat()},
        {'start': str(int(start_dt.timestamp())), 'end': str(int(end_dt.timestamp()))},
    ]


def fetch_attendance(client: WhenIWorkClient, start: date, end: date) -> tuple[list[dict], str, str]:
    errors = []
    for query in _time_query_candidates(start, end):
        try:
            entries = unwrap_entries(client.get('/times', params=query))
            return entries, 'wiw_times', ''
        except WhenIWorkError as exc:
            errors.append(str(exc))
            if '(400)' not in str(exc):
                break
    try:
        entries = client.collection('shifts', params={'start': start.isoformat(), 'end': end.isoformat()}, optional=False).items
        return entries, 'wiw_shifts', 'Attendance nicht verfügbar; geplante Schichten wurden verwendet.'
    except WhenIWorkError as exc:
        errors.append(str(exc))
        raise WhenIWorkError('Arbeitszeitdaten konnten nicht geladen werden: ' + ' | '.join(errors[-3:])) from exc


def ensure_settings() -> int:
    created = 0
    workers = WorkerProfile.objects.select_related('user').filter(active=True)
    for worker in workers:
        _, was_created = WorkingTimeSetting.objects.get_or_create(
            worker=worker,
            defaults={
                'monthly_limit': worker.monthly_hours or settings.WORKING_TIME_DEFAULT_MONTHLY_LIMIT,
                'hourly_rate': worker.tariff_hourly_rate or settings.WORKING_TIME_DEFAULT_HOURLY_RATE,
            },
        )
        created += int(was_created)
    return created


def _worker_for_entry(entry: dict, workers_by_id: dict[str, WorkerProfile]) -> WorkerProfile | None:
    candidate = first_value(entry, ('user_id', 'userid', 'userId', 'employee_id', 'employeeId'))
    if isinstance(candidate, dict):
        candidate = candidate.get('id')
    if candidate is None and isinstance(entry.get('user'), dict):
        candidate = entry['user'].get('id')
    return workers_by_id.get(str(candidate)) if candidate not in (None, '') else None


def sync_working_time(start: date, end: date, client=None) -> WorkingTimeSyncLog:
    if end < start:
        raise ValueError('Das Enddatum muss nach dem Startdatum liegen.')
    ensure_settings()
    wiw = client or WhenIWorkClient()
    entries, source, warning = fetch_attendance(wiw, start, end + timedelta(days=1))
    workers = list(WorkerProfile.objects.select_related('user').filter(active=True).exclude(wiw_user_id__isnull=True))
    workers_by_id = {str(worker.wiw_user_id): worker for worker in workers if worker.wiw_user_id}
    settings_map = {row.worker_id: row for row in WorkingTimeSetting.objects.select_related('worker').all()}
    grouped: dict[tuple[str, date], list[dict]] = defaultdict(list)
    hours_by_key: dict[tuple[str, date], Decimal] = defaultdict(lambda: Decimal('0'))
    fallback_break = settings.WORKING_TIME_DEFAULT_BREAK_MINUTES

    for entry in entries:
        worker = _worker_for_entry(entry, workers_by_id)
        if not worker:
            continue
        hours, started, _ = entry_hours(entry, source=source, fallback_break_minutes=fallback_break)
        if not started or started.date() < start or started.date() > end:
            continue
        key = (str(worker.id), started.date().replace(day=1))
        hours_by_key[key] += hours
        grouped[key].append(entry)

    now = timezone.now()
    count = 0
    with transaction.atomic():
        for worker in workers:
            row_setting = settings_map.get(worker.id)
            if row_setting and (not row_setting.active or row_setting.excluded):
                continue
            monthly_limit = dec((row_setting.monthly_limit if row_setting else None) or worker.monthly_hours or settings.WORKING_TIME_DEFAULT_MONTHLY_LIMIT)
            hourly_rate = dec((row_setting.hourly_rate if row_setting else None) or worker.tariff_hourly_rate or settings.WORKING_TIME_DEFAULT_HOURLY_RATE)
            carry = Decimal('0.00')
            prior = WorkingTimeAccountRecord.objects.filter(worker=worker, year_month__lt=start.replace(day=1)).order_by('-year_month').first()
            if prior:
                carry = prior.saldo_cumulative
            for month in iter_months(start, end):
                existing = WorkingTimeAccountRecord.objects.filter(worker=worker, year_month=month).first()
                ist = hours_by_key.get((str(worker.id), month), Decimal('0')).quantize(TWO)
                difference = (ist - monthly_limit).quantize(TWO)
                paid = existing.paid_hours if existing else Decimal('0')
                manual = existing.manual_adjustment if existing else Decimal('0')
                saldo = (carry + difference + manual - paid).quantize(TWO)
                gross = (ist * hourly_rate).quantize(TWO)
                WorkingTimeAccountRecord.objects.update_or_create(
                    worker=worker,
                    year_month=month,
                    defaults={
                        'ist_hours': ist,
                        'soll_hours': monthly_limit,
                        'difference_hours': difference,
                        'carryover_previous': carry,
                        'paid_hours': paid,
                        'manual_adjustment': manual,
                        'saldo_cumulative': saldo,
                        'hourly_rate': hourly_rate,
                        'gross_amount': gross,
                        'raw_entries': grouped.get((str(worker.id), month), []),
                        'source': source,
                        'synced_at': now,
                    },
                )
                carry = saldo
                count += 1
        log = WorkingTimeSyncLog.objects.create(
            range_start=start,
            range_end=end,
            status='warning' if warning else 'ok',
            message=warning,
            records_count=count,
            metadata={'source': source, 'entries': len(entries)},
        )
    return log


def _paid_total(row: WorkingTimeAccountRecord) -> Decimal:
    if row.paid_total_hours is not None:
        return dec(row.paid_total_hours)
    return (dec(row.soll_hours) + dec(row.paid_hours)).quantize(TWO)


def update_record(
    record: WorkingTimeAccountRecord,
    *,
    paid_total_hours=None,
    paid_hours=None,
    manual_adjustment=None,
) -> WorkingTimeAccountRecord:
    # paid_total_hours is the new unambiguous field. paid_hours remains accepted
    # for compatibility with older clients and means legacy extra hours.
    if paid_total_hours is not None:
        record.paid_total_hours = max(Decimal('0'), dec(paid_total_hours))
    elif paid_hours is not None:
        record.paid_hours = max(Decimal('0'), dec(paid_hours))
        record.paid_total_hours = (record.soll_hours + record.paid_hours).quantize(TWO)
    elif record.paid_total_hours is None:
        record.paid_total_hours = (record.soll_hours + record.paid_hours).quantize(TWO)

    if manual_adjustment is not None:
        record.manual_adjustment = dec(manual_adjustment)

    previous = (
        WorkingTimeAccountRecord.objects
        .filter(worker=record.worker, year_month__lt=record.year_month)
        .order_by('-year_month')
        .first()
    )
    record.carryover_previous = previous.saldo_cumulative if previous else Decimal('0')
    record.saldo_cumulative = (
        record.carryover_previous
        + record.ist_hours
        + record.manual_adjustment
        - _paid_total(record)
    ).quantize(TWO)
    record.save(update_fields=[
        'paid_hours', 'paid_total_hours', 'manual_adjustment',
        'carryover_previous', 'saldo_cumulative', 'updated_at',
    ])

    carry = record.saldo_cumulative
    for row in (
        WorkingTimeAccountRecord.objects
        .filter(worker=record.worker, year_month__gt=record.year_month)
        .order_by('year_month')
    ):
        row.carryover_previous = carry
        if row.paid_total_hours is None:
            row.paid_total_hours = (row.soll_hours + row.paid_hours).quantize(TWO)
        row.saldo_cumulative = (
            carry + row.ist_hours + row.manual_adjustment - _paid_total(row)
        ).quantize(TWO)
        row.save(update_fields=[
            'paid_total_hours', 'carryover_previous', 'saldo_cumulative', 'updated_at',
        ])
        carry = row.saldo_cumulative
    return record


def _entry_totals(raw_entries: list[dict]) -> dict:
    totals = {
        'worked_minutes': 0,
        'break_minutes': 0,
        'night_minutes': 0,
        'saturday_minutes': 0,
        'sunday_minutes': 0,
        'night_surcharge_amount': Decimal('0.00'),
        'saturday_surcharge_amount': Decimal('0.00'),
        'sunday_surcharge_amount': Decimal('0.00'),
    }
    for entry in raw_entries or []:
        for key in ('worked_minutes', 'break_minutes', 'night_minutes', 'saturday_minutes', 'sunday_minutes'):
            totals[key] += int(entry.get(key) or 0)
        for key in ('night_surcharge_amount', 'saturday_surcharge_amount', 'sunday_surcharge_amount'):
            totals[key] += dec(entry.get(key) or 0)
    totals['surcharge_amount'] = (
        totals['night_surcharge_amount']
        + totals['saturday_surcharge_amount']
        + totals['sunday_surcharge_amount']
    ).quantize(TWO)
    return totals


def _minijob_limit(year_month: date) -> Decimal | None:
    # Historical values used only for an informational warning in the audit UI.
    # The classification remains a payroll/tax decision and is never auto-changed.
    limits = {
        2024: Decimal('538.00'),
        2025: Decimal('556.00'),
        2026: Decimal('603.00'),
    }
    return limits.get(year_month.year)


def statement_dict(statement: PayrollStatement | None) -> dict | None:
    if not statement:
        return None
    return {
        'id': str(statement.id),
        'gross_amount': str(statement.gross_amount) if statement.gross_amount is not None else None,
        'net_amount': str(statement.net_amount) if statement.net_amount is not None else None,
        'transferred_amount': str(statement.transferred_amount) if statement.transferred_amount is not None else None,
        'payment_date': statement.payment_date.isoformat() if statement.payment_date else None,
        'source': statement.source,
        'source_reference': statement.source_reference,
        'document_url': statement.document.url if statement.document else '',
    }


def record_dict(
    row: WorkingTimeAccountRecord,
    statement: PayrollStatement | None = None,
    *,
    include_entries: bool = False,
) -> dict:
    totals = _entry_totals(row.raw_entries or [])
    paid_total = _paid_total(row)
    monthly_balance = (row.ist_hours + row.manual_adjustment - paid_total).quantize(TWO)
    surcharge_amount = totals['surcharge_amount']
    gross_with_surcharges = (row.gross_amount + surcharge_amount).quantize(TWO)
    minijob_limit = _minijob_limit(row.year_month) if row.worker.employment_type == WorkerProfile.EmploymentType.MINI else None
    result = {
        'id': str(row.id),
        'worker_id': str(row.worker_id),
        'employee_name': str(row.worker.user),
        'employee_number': row.worker.employee_number,
        'employment_type': row.worker.employment_type,
        'wiw_user_id': row.worker.wiw_user_id,
        'year_month': row.year_month.strftime('%Y-%m'),
        'ist_hours': str(row.ist_hours),
        'soll_hours': str(row.soll_hours),
        'difference_hours': str(row.difference_hours),
        'carryover_previous': str(row.carryover_previous),
        'paid_hours': str(row.paid_hours),
        'paid_total_hours': str(paid_total),
        'monthly_balance_hours': str(monthly_balance),
        'manual_adjustment': str(row.manual_adjustment),
        'saldo_cumulative': str(row.saldo_cumulative),
        'hourly_rate': str(row.hourly_rate),
        'gross_amount': str(row.gross_amount),
        'gross_with_surcharges': str(gross_with_surcharges),
        'worked_minutes': totals['worked_minutes'],
        'break_minutes': totals['break_minutes'],
        'night_hours': str((Decimal(totals['night_minutes']) / Decimal('60')).quantize(TWO)),
        'saturday_hours': str((Decimal(totals['saturday_minutes']) / Decimal('60')).quantize(TWO)),
        'sunday_hours': str((Decimal(totals['sunday_minutes']) / Decimal('60')).quantize(TWO)),
        'night_surcharge_amount': str(totals['night_surcharge_amount'].quantize(TWO)),
        'saturday_surcharge_amount': str(totals['saturday_surcharge_amount'].quantize(TWO)),
        'sunday_surcharge_amount': str(totals['sunday_surcharge_amount'].quantize(TWO)),
        'surcharge_amount': str(surcharge_amount),
        'entry_count': len(row.raw_entries or []),
        'source': row.source,
        'synced_at': row.synced_at.isoformat() if row.synced_at else None,
        'payroll_statement': statement_dict(statement),
        'minijob_limit': str(minijob_limit) if minijob_limit is not None else None,
        # Informational only. Use base gross here because treatment of supplements
        # in the Minijob earnings test depends on the payroll/tax classification.
        'minijob_warning': bool(minijob_limit is not None and row.gross_amount > minijob_limit),
    }
    if include_entries:
        result['entries'] = row.raw_entries or []
    return result


def settings_rows() -> list[dict]:
    ensure_settings()
    rows = WorkingTimeSetting.objects.select_related('worker__user').order_by('worker__user__last_name', 'worker__user__first_name')
    return [{
        'id': str(item.id),
        'worker_id': str(item.worker_id),
        'wiw_user_id': item.worker.wiw_user_id,
        'employee_name': str(item.worker.user),
        'employment_type': item.worker.employment_type,
        'monthly_limit': str(item.monthly_limit),
        'hourly_rate': str(item.hourly_rate),
        'night_surcharge_percent': str(item.night_surcharge_percent),
        'saturday_surcharge_percent': str(item.saturday_surcharge_percent),
        'sunday_surcharge_percent': str(item.sunday_surcharge_percent),
        'active': item.active,
        'excluded': item.excluded,
        'notes': item.notes,
    } for item in rows]


def _statement_map(rows: list[WorkingTimeAccountRecord]) -> dict[tuple[str, date], PayrollStatement]:
    worker_ids = {row.worker_id for row in rows}
    if not worker_ids:
        return {}
    periods = {row.year_month for row in rows}
    statements = PayrollStatement.objects.filter(worker_id__in=worker_ids, period__in=periods)
    return {(str(item.worker_id), item.period): item for item in statements}


def export_csv(queryset) -> HttpResponse:
    rows = list(queryset.select_related('worker__user'))
    statements = _statement_map(rows)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'Mitarbeiter', 'Beschäftigung', 'Monat', 'Ist-Stunden', 'Soll-Stunden',
        'Bezahlte Stunden gesamt', 'Zusätzlich ausgezahlte Stunden', 'Monatssaldo',
        'Übertrag', 'Saldo kumuliert', 'Stundensatz', 'Brutto Basis',
        'Nachtstunden', 'Samstagsstunden', 'Sonntagsstunden', 'Zuschläge',
        'Brutto inkl. Zuschläge', 'Lexware überwiesen', 'Lexware Zahlungsdatum',
    ])
    for row in rows:
        statement = statements.get((str(row.worker_id), row.year_month))
        data = record_dict(row, statement)
        payroll = data.get('payroll_statement') or {}
        writer.writerow([
            data['employee_name'], data['employment_type'], data['year_month'],
            data['ist_hours'], data['soll_hours'], data['paid_total_hours'], data['paid_hours'],
            data['monthly_balance_hours'], data['carryover_previous'], data['saldo_cumulative'],
            data['hourly_rate'], data['gross_amount'], data['night_hours'], data['saturday_hours'],
            data['sunday_hours'], data['surcharge_amount'], data['gross_with_surcharges'],
            payroll.get('transferred_amount') or '', payroll.get('payment_date') or '',
        ])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="arbeitszeit-lohnkonto.csv"'
    return response


def export_xlsx(queryset) -> HttpResponse:
    rows = list(queryset.select_related('worker__user'))
    statements = _statement_map(rows)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Arbeitszeit & Lohnkonto'
    headers = [
        'Mitarbeiter', 'Beschäftigung', 'Monat', 'Ist-Stunden', 'Soll-Stunden',
        'Bezahlte Stunden gesamt', 'Zusätzlich ausgezahlt', 'Monatssaldo',
        'Übertrag', 'Saldo kumuliert', 'Stundensatz', 'Brutto Basis',
        'Nachtstunden', 'Samstagsstunden', 'Sonntagsstunden', 'Zuschläge',
        'Brutto inkl. Zuschläge', 'Lexware überwiesen', 'Lexware Zahlungsdatum',
    ]
    ws.append(headers)
    for row in rows:
        data = record_dict(row, statements.get((str(row.worker_id), row.year_month)))
        payroll = data.get('payroll_statement') or {}
        ws.append([
            data['employee_name'], data['employment_type'], data['year_month'],
            float(data['ist_hours']), float(data['soll_hours']), float(data['paid_total_hours']),
            float(data['paid_hours']), float(data['monthly_balance_hours']),
            float(data['carryover_previous']), float(data['saldo_cumulative']),
            float(data['hourly_rate']), float(data['gross_amount']), float(data['night_hours']),
            float(data['saturday_hours']), float(data['sunday_hours']), float(data['surcharge_amount']),
            float(data['gross_with_surcharges']),
            float(payroll['transferred_amount']) if payroll.get('transferred_amount') else None,
            payroll.get('payment_date') or '',
        ])
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = min(max(len(str(cell.value or '')) for cell in column) + 2, 32)
    buffer = io.BytesIO()
    wb.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="arbeitszeit-lohnkonto.xlsx"'
    return response


def _pdf_dt(value):
    parsed = parse_dt(value)
    return parsed


def _pdf_clock(value):
    parsed = _pdf_dt(value)
    return parsed.strftime('%H:%M') if parsed else '–'


def _pdf_date(value):
    parsed = _pdf_dt(value)
    return parsed.strftime('%d.%m.%Y') if parsed else '–'


def _pdf_hours(minutes) -> str:
    total = max(0, int(minutes or 0))
    return f'{total // 60}:{total % 60:02d}'


def worker_pdf(worker: WorkerProfile, queryset) -> bytes:
    rows = list(queryset.select_related('worker__user'))
    statements = _statement_map(rows)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='WTTitle', parent=styles['Title'], alignment=TA_CENTER, spaceAfter=12))
    styles.add(ParagraphStyle(name='WTMonth', parent=styles['Heading2'], spaceBefore=4, spaceAfter=6))
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    story = [
        Paragraph('Arbeitszeit und Lohnkonto', styles['WTTitle']),
        Paragraph(f'{worker.user} · {worker.get_employment_type_display()}', styles['Heading2']),
        Spacer(1, 8),
    ]

    data = [[
        'Monat', 'Ist', 'Soll', 'Bezahlt', 'Monatssaldo', 'Übertrag', 'Saldo',
        'Nacht', 'Sa.', 'So.', 'Zuschläge', 'Brutto', 'Überwiesen',
    ]]
    for row in rows:
        item = record_dict(row, statements.get((str(row.worker_id), row.year_month)))
        payroll = item.get('payroll_statement') or {}
        data.append([
            row.year_month.strftime('%m/%Y'), item['ist_hours'], item['soll_hours'],
            item['paid_total_hours'], item['monthly_balance_hours'], item['carryover_previous'],
            item['saldo_cumulative'], item['night_hours'], item['saturday_hours'], item['sunday_hours'],
            f"{item['surcharge_amount']} €", f"{item['gross_with_surcharges']} €",
            f"{payroll.get('transferred_amount')} €" if payroll.get('transferred_amount') else '–',
        ])
    table = Table(data, repeatRows=1, colWidths=[20 * mm] + [19 * mm] * 12)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#163B65')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#CCD5E0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FC')]),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(table)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        'IST basiert auf tatsächlichen freigegebenen A+ Zeiten und historischem WIW Altbestand. '
        'Dienstplanzeiten dienen nur als Vergleich. Bezahlt sind die tatsächlich für den Monat '
        'hinterlegten bezahlten Stunden. Zuschläge verwenden die je Mitarbeiter hinterlegten Prozentsätze.',
        styles['BodyText'],
    ))

    for row_index, row in enumerate(rows):
        entries = sorted(
            list(row.raw_entries or []),
            key=lambda item: str(item.get('local_clock_in') or item.get('clock_in') or ''),
        )
        if not entries:
            continue
        story.append(PageBreak())
        statement = statements.get((str(row.worker_id), row.year_month))
        item = record_dict(row, statement)
        payroll = item.get('payroll_statement') or {}
        story.append(Paragraph(row.year_month.strftime('%m/%Y'), styles['WTMonth']))
        story.append(Paragraph(
            f"Gearbeitet: {item['ist_hours']} Std. · Bezahlt: {item['paid_total_hours']} Std. · "
            f"Saldo Monat: {item['monthly_balance_hours']} Std. · Saldo kumuliert: {item['saldo_cumulative']} Std. · "
            f"Stundensatz: {item['hourly_rate']} € · Brutto mit Zuschlägen: {item['gross_with_surcharges']} € · "
            f"Lexware überwiesen: {payroll.get('transferred_amount') or '–'} €",
            styles['BodyText'],
        ))
        story.append(Spacer(1, 6))
        detail = [['Datum', 'Kunde / Ort', 'Plan', 'Ist', 'Pause', 'Netto', 'Nacht', 'Sa.', 'So.']]
        for entry in entries:
            client = str(entry.get('client_name') or 'Ohne Zuordnung')
            location = str(entry.get('location_name') or entry.get('position_name') or '')
            if location:
                client = f'{client} / {location}'
            detail.append([
                _pdf_date(entry.get('local_clock_in') or entry.get('clock_in')),
                client,
                f"{_pdf_clock(entry.get('planned_start'))} bis {_pdf_clock(entry.get('planned_end'))}",
                f"{_pdf_clock(entry.get('local_clock_in') or entry.get('clock_in'))} bis {_pdf_clock(entry.get('local_clock_out') or entry.get('clock_out'))}",
                f"{int(entry.get('break_minutes') or 0)} Min.",
                _pdf_hours(entry.get('worked_minutes')),
                _pdf_hours(entry.get('night_minutes')),
                _pdf_hours(entry.get('saturday_minutes')),
                _pdf_hours(entry.get('sunday_minutes')),
            ])
        detail_table = Table(
            detail,
            repeatRows=1,
            colWidths=[23 * mm, 55 * mm, 30 * mm, 30 * mm, 20 * mm, 20 * mm, 20 * mm, 17 * mm, 17 * mm],
        )
        detail_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#163B65')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#CCD5E0')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FC')]),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(detail_table)

    doc.build(story)
    return buffer.getvalue()


def create_backup(kind='manual') -> dict:
    backup_dir = Path(settings.MEDIA_ROOT) / 'backups' / 'working-time'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
    path = backup_dir / f'arbeitszeitkonto-{kind}-{stamp}.json'
    payload = {
        'version': 1,
        'created_at': timezone.now().isoformat(),
        'kind': kind,
        'settings': settings_rows(),
        'records': [record_dict(item) for item in WorkingTimeAccountRecord.objects.select_related('worker__user').order_by('worker__employee_number', 'year_month')],
        'logs': list(WorkingTimeSyncLog.objects.values('range_start', 'range_end', 'status', 'message', 'records_count', 'metadata', 'created_at')[:100]),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding='utf-8')
    backups = sorted(backup_dir.glob('arbeitszeitkonto-*.json'), key=lambda item: item.stat().st_mtime, reverse=True)
    for old in backups[30:]:
        old.unlink(missing_ok=True)
    return {'path': str(path.relative_to(settings.MEDIA_ROOT)), 'records': len(payload['records']), 'settings': len(payload['settings'])}
