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
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
    EmployeeMasterData,
    PayrollStatement,
    TimeOffRequest,
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


def _statement_payslip(statement: PayrollStatement | None) -> dict:
    if not statement:
        return {}
    payslips = [
        item for item in list(statement.raw_data or [])
        if item.get('kind') == 'payslip'
    ]
    if not payslips:
        return {}
    return max(
        enumerate(payslips),
        key=lambda pair: (bool(pair[1].get('is_correction')), pair[0]),
    )[1]


def _statement_compensation_type(statement: PayrollStatement | None) -> str:
    return str(_statement_payslip(statement).get('compensation_type') or '').strip().lower()


def _paid_total(row: WorkingTimeAccountRecord, statement: PayrollStatement | None = None) -> Decimal:
    if row.paid_total_hours is not None:
        return dec(row.paid_total_hours)
    compensation_type = _statement_compensation_type(statement) or _compensation_type(row.worker)
    if compensation_type == 'salary':
        return Decimal('0.00')
    return (dec(row.soll_hours) + dec(row.paid_hours)).quantize(TWO)


def _compensation_type(worker: WorkerProfile) -> str:
    try:
        return str((worker.master_data.data or {}).get('compensation_type') or '').strip().lower()
    except Exception:
        master = EmployeeMasterData.objects.filter(worker=worker).only('data').first()
        return str((master.data or {}).get('compensation_type') or '').strip().lower() if master else ''


def _balance_reference(
    row: WorkingTimeAccountRecord,
    statement: PayrollStatement | None = None,
) -> tuple[Decimal, str]:
    compensation_type = _statement_compensation_type(statement) or _compensation_type(row.worker)
    if compensation_type == 'salary':
        return dec(row.soll_hours), 'soll_salary'
    return _paid_total(row, statement), 'paid_hours'


def update_record(
    record: WorkingTimeAccountRecord,
    *,
    paid_total_hours=None,
    paid_hours=None,
    manual_adjustment=None,
) -> WorkingTimeAccountRecord:
    # paid_total_hours is the new unambiguous field. paid_hours remains accepted
    # for compatibility with older clients and means legacy extra hours.
    statement_map = {
        item.period: item
        for item in PayrollStatement.objects.filter(worker=record.worker)
    }
    record_statement = statement_map.get(record.year_month)
    record_compensation = (
        _statement_compensation_type(record_statement)
        or _compensation_type(record.worker)
    )

    if paid_total_hours is not None:
        record.paid_total_hours = max(Decimal('0'), dec(paid_total_hours))
    elif paid_hours is not None:
        record.paid_hours = max(Decimal('0'), dec(paid_hours))
        record.paid_total_hours = (record.soll_hours + record.paid_hours).quantize(TWO)
    elif record.paid_total_hours is None and record_compensation != 'salary':
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
        - _balance_reference(record, record_statement)[0]
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
        row_statement = statement_map.get(row.year_month)
        row_compensation = (
            _statement_compensation_type(row_statement)
            or _compensation_type(row.worker)
        )
        if row.paid_total_hours is None and row_compensation != 'salary':
            row.paid_total_hours = (row.soll_hours + row.paid_hours).quantize(TWO)
        row.saldo_cumulative = (
            carry
            + row.ist_hours
            + row.manual_adjustment
            - _balance_reference(row, row_statement)[0]
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
    raw_items = list(statement.raw_data or [])
    payslips = [item for item in raw_items if item.get('kind') == 'payslip']

    # Corrections are authoritative for payroll/accounting values, while a
    # zero payout on a correction page usually means "already settled" rather
    # than "nothing was transferred this month". Keep the original non-zero
    # payout for reconciliation with Zahlungsliste/SEPA in that case.
    indexed_payslips = list(enumerate(payslips))
    accounting_payslip = (
        max(
            indexed_payslips,
            key=lambda pair: (bool(pair[1].get('is_correction')), pair[0]),
        )[1]
        if indexed_payslips
        else {}
    )
    payout_payslip = accounting_payslip
    if (
        accounting_payslip.get('is_correction')
        and dec(accounting_payslip.get('payout_amount')) == Decimal('0.00')
    ):
        original_nonzero = [
            item for item in payslips
            if not item.get('is_correction')
            and item.get('payout_amount') not in (None, '')
            and dec(item.get('payout_amount')) > Decimal('0.00')
        ]
        if original_nonzero:
            payout_payslip = original_nonzero[-1]

    return {
        'id': str(statement.id),
        'gross_amount': str(statement.gross_amount) if statement.gross_amount is not None else None,
        'net_amount': str(statement.net_amount) if statement.net_amount is not None else None,
        'transferred_amount': str(statement.transferred_amount) if statement.transferred_amount is not None else None,
        'payment_date': statement.payment_date.isoformat() if statement.payment_date else None,
        'source': statement.source,
        'source_reference': statement.source_reference,
        'document_url': statement.document.url if statement.document else '',
        'lexware_compensation_type': accounting_payslip.get('compensation_type') or '',
        'lexware_paid_hours': accounting_payslip.get('quantity') if accounting_payslip.get('compensation_type') == 'hourly' else None,
        'lexware_hourly_rate': accounting_payslip.get('hourly_rate'),
        'lexware_monthly_salary': accounting_payslip.get('monthly_salary'),
        'lexware_payout_amount': payout_payslip.get('payout_amount'),
        'lexware_correction_payout_amount': (
            accounting_payslip.get('payout_amount')
            if accounting_payslip.get('is_correction')
            else None
        ),
        'lexware_is_correction': bool(accounting_payslip.get('is_correction')),
        'lexware_personal_number': accounting_payslip.get('personal_number') or '',
        'lexware_person_group': accounting_payslip.get('person_group') or '',
        'lexware_supplements': accounting_payslip.get('supplements') or [],
    }


def absence_summary_map(rows: list[WorkingTimeAccountRecord]) -> dict[tuple[str, date], dict]:
    """Approved A+ absences by employee/month.

    These values are informational and never change IST or payroll saldo
    automatically. Free-text reasons are classified conservatively.
    """
    if not rows:
        return {}
    worker_ids = {row.worker_id for row in rows}
    first_month = min(row.year_month for row in rows)
    last_month = max(row.year_month for row in rows)
    last_day = next_month(last_month) - timedelta(days=1)
    requests = TimeOffRequest.objects.filter(
        worker_id__in=worker_ids,
        status=TimeOffRequest.Status.APPROVED,
        starts_on__lte=last_day,
        ends_on__gte=first_month,
    ).order_by('starts_on')

    buckets: dict[tuple[str, date], dict] = {}
    for request in requests:
        reason = str(request.reason or '').strip()
        reason_key = reason.lower()
        if any(token in reason_key for token in ('krank', 'arbeitsunfähig', 'arbeitsunfaehig', 'au ', 'krankheit')):
            category = 'sick'
        elif any(token in reason_key for token in ('urlaub', 'vacation', 'ferien')):
            category = 'vacation'
        else:
            category = 'other'

        current = max(request.starts_on, first_month)
        request_end = min(request.ends_on, last_day)
        while current <= request_end:
            month = current.replace(day=1)
            month_end = next_month(month) - timedelta(days=1)
            overlap_end = min(request_end, month_end)
            key = (str(request.worker_id), month)
            bucket = buckets.setdefault(key, {
                'all_dates': set(),
                'vacation_dates': set(),
                'sick_dates': set(),
                'other_dates': set(),
                'details': [],
            })
            cursor = current
            while cursor <= overlap_end:
                bucket['all_dates'].add(cursor)
                bucket[f'{category}_dates'].add(cursor)
                cursor += timedelta(days=1)
            bucket['details'].append({
                'from': current.isoformat(),
                'to': overlap_end.isoformat(),
                'reason': reason,
                'category': category,
            })
            current = overlap_end + timedelta(days=1)

    result = {}
    for key, bucket in buckets.items():
        result[key] = {
            'absence_days': len(bucket['all_dates']),
            'vacation_days': len(bucket['vacation_dates']),
            'sick_days': len(bucket['sick_dates']),
            'other_absence_days': len(bucket['other_dates']),
            'absence_details': bucket['details'],
        }
    return result


def record_dict(
    row: WorkingTimeAccountRecord,
    statement: PayrollStatement | None = None,
    *,
    include_entries: bool = False,
    absence_summary: dict | None = None,
) -> dict:
    totals = _entry_totals(row.raw_entries or [])
    paid_total = _paid_total(row, statement)
    balance_reference, balance_basis = _balance_reference(row, statement)
    payroll_statement = statement_dict(statement)
    is_open_month = (
        row.year_month >= timezone.localdate().replace(day=1)
        and statement is None
        and dec(row.ist_hours) == Decimal('0.00')
    )
    if is_open_month:
        balance_reference = Decimal('0.00')
        balance_basis = 'open_month'
        monthly_balance = Decimal('0.00')
        displayed_saldo = dec(row.carryover_previous)
    else:
        monthly_balance = (
            row.ist_hours + row.manual_adjustment - balance_reference
        ).quantize(TWO)
        displayed_saldo = dec(row.saldo_cumulative)
    surcharge_amount = totals['surcharge_amount']
    gross_with_surcharges = (row.gross_amount + surcharge_amount).quantize(TWO)
    employment_type = row.employment_type_snapshot or row.worker.employment_type
    # Lexware person group 109 is an authoritative Minijob marker for that
    # payroll month. A non-109 group is equally authoritative that the month
    # must not be checked against the Minijob earnings ceiling, even if the
    # current/snapshotted A+ employment label is stale.
    lexware_person_group = str(
        (payroll_statement or {}).get('lexware_person_group') or ''
    ).strip()
    if lexware_person_group == '109':
        employment_type = WorkerProfile.EmploymentType.MINI
    is_minijob_month = (
        lexware_person_group == '109'
        or (
            not lexware_person_group
            and employment_type == WorkerProfile.EmploymentType.MINI
        )
    )
    minijob_limit = _minijob_limit(row.year_month) if is_minijob_month else None
    result = {
        'id': str(row.id),
        'worker_id': str(row.worker_id),
        'employee_name': str(row.worker.user),
        'employee_number': row.worker.employee_number,
        'employment_type': employment_type,
        'wiw_user_id': row.worker.wiw_user_id,
        'year_month': row.year_month.strftime('%Y-%m'),
        'ist_hours': str(row.ist_hours),
        'soll_hours': str(row.soll_hours),
        'difference_hours': str(row.difference_hours),
        'carryover_previous': str(row.carryover_previous),
        'paid_hours': str(row.paid_hours),
        'paid_total_hours': str(paid_total),
        'balance_basis': balance_basis,
        'balance_reference_hours': str(balance_reference),
        'monthly_balance_hours': str(monthly_balance),
        'manual_adjustment': str(row.manual_adjustment),
        'saldo_cumulative': str(displayed_saldo),
        'is_open_month': is_open_month,
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
        'payroll_statement': payroll_statement,
        'minijob_limit': str(minijob_limit) if minijob_limit is not None else None,
        # Informational only. Use base gross here because treatment of supplements
        # in the Minijob earnings test depends on the payroll/tax classification.
        'minijob_warning': bool(minijob_limit is not None and row.gross_amount > minijob_limit),
        'absence_days': int((absence_summary or {}).get('absence_days') or 0),
        'vacation_days': int((absence_summary or {}).get('vacation_days') or 0),
        'sick_days': int((absence_summary or {}).get('sick_days') or 0),
        'other_absence_days': int((absence_summary or {}).get('other_absence_days') or 0),
        'absence_details': list((absence_summary or {}).get('absence_details') or []),
    }

    contract_issues = []
    master_data = _worker_master_data(row.worker)
    latest_master_period = str(master_data.get('lexware_latest_payroll_period') or '').strip()
    is_current_master_period = (
        not latest_master_period
        or row.year_month.strftime('%Y-%m') == latest_master_period
    )

    # Current master data must not be compared against old payroll months.
    # Employees can legitimately move from hourly/minijob to salary/full-time,
    # as happened in the imported 2026 history. Historical Lexware payslips are
    # authoritative for their own month; only the latest payroll month is
    # checked against the current A+ master data.
    app_compensation = _compensation_type(row.worker)
    lexware_compensation = str(
        (payroll_statement or {}).get('lexware_compensation_type') or ''
    ).strip().lower()
    compensation_labels = {
        'salary': 'Gehalt',
        'hourly': 'Stundenlohn',
    }
    if is_current_master_period and lexware_compensation:
        if app_compensation and lexware_compensation != app_compensation:
            contract_issues.append(
                'Vergütungsart stimmt nicht überein: '
                f"A+ {compensation_labels.get(app_compensation, app_compensation)}, "
                f"Lexware {compensation_labels.get(lexware_compensation, lexware_compensation)}."
            )
        elif not app_compensation:
            contract_issues.append(
                'Vergütungsart in A+ fehlt. '
                f"Lexware weist {compensation_labels.get(lexware_compensation, lexware_compensation)} aus."
            )

    lexware_employment = str(master_data.get('employment_type_lexware') or '').strip().lower()
    if (
        is_current_master_period
        and 'minijob' in lexware_employment
        and employment_type != WorkerProfile.EmploymentType.MINI
    ):
        contract_issues.append(
            f'Lexware Stammdaten weisen Minijob aus, A+ ist als {employment_type} gespeichert.'
        )
    if result['minijob_warning']:
        contract_issues.append(
            f"Minijob prüfen: Grundbrutto {row.gross_amount} € liegt über {minijob_limit} €."
        )

    result['contract_issues'] = contract_issues
    result['surcharge_reconciliation'] = _surcharge_reconciliation(result)
    if is_open_month:
        result['reconciliation_status'] = 'LAUFEND'
        result['reconciliation_issues'] = []
    else:
        reconciliation_status, reconciliation_issues = _reconciliation_status(result)
        result['reconciliation_status'] = reconciliation_status
        result['reconciliation_issues'] = reconciliation_issues

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
    absences = absence_summary_map(rows)
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    # Preserve the historical first eleven columns for downstream payroll
    # workbooks; append richer audit fields instead of shifting old indexes.
    writer.writerow([
        'Mitarbeiter', 'Monat', 'Ist-Stunden', 'Soll-Stunden', 'Plusstunden',
        'Übertrag', 'Ausbezahlt', 'Korrektur', 'Saldo', 'Stundensatz', 'Brutto',
        'Beschäftigung', 'Bezahlte Stunden gesamt', 'Monatssaldo',
        'Nachtstunden', 'Samstagsstunden', 'Sonntagsstunden', 'Zuschläge',
        'Brutto inkl. Zuschläge', 'Lexware Brutto', 'Lexware Netto',
        'Lexware Auszahlung', 'Lexware Zahlungsdatum', 'Vergütungsart',
        'Abgleich Status', 'Prüfhinweise', 'Nacht Abgleich',
        'Samstag Abgleich', 'Sonntag Abgleich',
        'Abwesenheit Tage', 'Urlaub Tage', 'Krank Tage', 'Sonstige Abwesenheit Tage',
    ])
    for row in rows:
        statement = statements.get((str(row.worker_id), row.year_month))
        data = record_dict(
            row,
            statement,
            absence_summary=absences.get((str(row.worker_id), row.year_month)),
        )
        payroll = data.get('payroll_statement') or {}
        writer.writerow([
            data['employee_name'], data['year_month'], data['ist_hours'],
            data['soll_hours'], data['difference_hours'], data['carryover_previous'],
            data['paid_hours'], data['manual_adjustment'], data['saldo_cumulative'],
            data['hourly_rate'], data['gross_amount'],
            data['employment_type'], data['paid_total_hours'], data['monthly_balance_hours'],
            data['night_hours'], data['saturday_hours'], data['sunday_hours'],
            data['surcharge_amount'], data['gross_with_surcharges'],
            payroll.get('gross_amount') or '', payroll.get('net_amount') or '',
            payroll.get('lexware_payout_amount') or payroll.get('transferred_amount') or '',
            payroll.get('payment_date') or '',
            payroll.get('lexware_compensation_type') or '',
            data.get('reconciliation_status') or '',
            ' | '.join(data.get('reconciliation_issues') or []),
            (data.get('surcharge_reconciliation') or {}).get('night', {}).get('status') or '',
            (data.get('surcharge_reconciliation') or {}).get('saturday', {}).get('status') or '',
            (data.get('surcharge_reconciliation') or {}).get('sunday', {}).get('status') or '',
            data.get('absence_days') or 0,
            data.get('vacation_days') or 0,
            data.get('sick_days') or 0,
            data.get('other_absence_days') or 0,
        ])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="arbeitszeit-lohnkonto.csv"'
    return response


def export_xlsx(queryset) -> HttpResponse:
    rows = list(queryset.select_related('worker__user'))
    statements = _statement_map(rows)
    absences = absence_summary_map(rows)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Arbeitszeitkonto'
    headers = [
        'Mitarbeiter', 'Monat', 'Ist-Stunden', 'Soll-Stunden', 'Plusstunden',
        'Übertrag', 'Ausbezahlt', 'Korrektur', 'Saldo', 'Stundensatz', 'Brutto',
        'Beschäftigung', 'Bezahlte Stunden gesamt', 'Monatssaldo',
        'Nachtstunden', 'Samstagsstunden', 'Sonntagsstunden', 'Zuschläge',
        'Brutto inkl. Zuschläge', 'Lexware Brutto', 'Lexware Netto',
        'Lexware Auszahlung', 'Lexware Zahlungsdatum', 'Vergütungsart',
        'Abgleich Status', 'Prüfhinweise', 'Nacht Abgleich',
        'Samstag Abgleich', 'Sonntag Abgleich',
        'Abwesenheit Tage', 'Urlaub Tage', 'Krank Tage', 'Sonstige Abwesenheit Tage',
    ]
    ws.append(headers)
    for row in rows:
        data = record_dict(
            row,
            statements.get((str(row.worker_id), row.year_month)),
            absence_summary=absences.get((str(row.worker_id), row.year_month)),
        )
        payroll = data.get('payroll_statement') or {}
        ws.append([
            data['employee_name'], data['year_month'], float(data['ist_hours']),
            float(data['soll_hours']), float(data['difference_hours']),
            float(data['carryover_previous']), float(data['paid_hours']),
            float(data['manual_adjustment']), float(data['saldo_cumulative']),
            float(data['hourly_rate']), float(data['gross_amount']),
            data['employment_type'], float(data['paid_total_hours']),
            float(data['monthly_balance_hours']), float(data['night_hours']),
            float(data['saturday_hours']), float(data['sunday_hours']),
            float(data['surcharge_amount']), float(data['gross_with_surcharges']),
            float(payroll['gross_amount']) if payroll.get('gross_amount') else None,
            float(payroll['net_amount']) if payroll.get('net_amount') else None,
            float(payroll.get('lexware_payout_amount') or payroll.get('transferred_amount')) if (payroll.get('lexware_payout_amount') or payroll.get('transferred_amount')) else None,
            payroll.get('payment_date') or '',
            payroll.get('lexware_compensation_type') or '',
            data.get('reconciliation_status') or '',
            ' | '.join(data.get('reconciliation_issues') or []),
            (data.get('surcharge_reconciliation') or {}).get('night', {}).get('status') or '',
            (data.get('surcharge_reconciliation') or {}).get('saturday', {}).get('status') or '',
            (data.get('surcharge_reconciliation') or {}).get('sunday', {}).get('status') or '',
            int(data.get('absence_days') or 0),
            int(data.get('vacation_days') or 0),
            int(data.get('sick_days') or 0),
            int(data.get('other_absence_days') or 0),
        ])
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = min(max(len(str(cell.value or '')) for cell in column) + 2, 32)
    buffer = io.BytesIO()
    wb.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="02_Lohnkonto_Gesamt.xlsx"'
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
    absences = absence_summary_map(rows)
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
        'Monat', 'Ist', 'Soll', 'Basis', 'Monatssaldo', 'Übertrag', 'Saldo',
        'Nacht', 'Sa.', 'So.', 'Abw.', 'Urlaub', 'Krank', 'Zuschläge', 'Brutto', 'Überwiesen',
    ]]
    for row in rows:
        item = record_dict(
            row,
            statements.get((str(row.worker_id), row.year_month)),
            absence_summary=absences.get((str(row.worker_id), row.year_month)),
        )
        payroll = item.get('payroll_statement') or {}
        data.append([
            row.year_month.strftime('%m/%Y'), item['ist_hours'], item['soll_hours'],
            item['balance_reference_hours'], item['monthly_balance_hours'], item['carryover_previous'],
            item['saldo_cumulative'], item['night_hours'], item['saturday_hours'], item['sunday_hours'],
            item['absence_days'], item['vacation_days'], item['sick_days'],
            f"{item['surcharge_amount']} €", f"{item['gross_with_surcharges']} €",
            f"{payroll.get('transferred_amount')} €" if payroll.get('transferred_amount') else '–',
        ])
    table = Table(data, repeatRows=1, colWidths=[18 * mm] + [16 * mm] * 15)
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
        item = record_dict(
            row,
            statement,
            absence_summary=absences.get((str(row.worker_id), row.year_month)),
        )
        payroll = item.get('payroll_statement') or {}
        story.append(Paragraph(row.year_month.strftime('%m/%Y'), styles['WTMonth']))
        basis_label = 'Sollbasis' if item.get('balance_basis') == 'soll_salary' else 'Bezahlt'
        compensation_text = (
            f"Gehalt: {payroll.get('lexware_monthly_salary') or row.gross_amount} €"
            if item.get('balance_basis') == 'soll_salary'
            else f"Stundensatz: {item['hourly_rate']} €"
        )
        story.append(Paragraph(
            f"Gearbeitet: {item['ist_hours']} Std. · {basis_label}: {item['balance_reference_hours']} Std. · "
            f"Saldo Monat: {item['monthly_balance_hours']} Std. · Saldo kumuliert: {item['saldo_cumulative']} Std. · "
            f"{compensation_text} · Brutto mit Zuschlägen: {item['gross_with_surcharges']} € · "
            f"Lexware überwiesen: {payroll.get('transferred_amount') or '–'} € · "
            f"Abwesenheit: {item['absence_days']} Tage (Urlaub {item['vacation_days']}, Krank {item['sick_days']})",
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


def _docx_bytes(document: Document) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _docx_style(document: Document):
    normal = document.styles['Normal']
    normal.font.name = 'Arial'
    normal.font.size = Pt(9)
    for section in document.sections:
        section.top_margin = Cm(1.4)
        section.bottom_margin = Cm(1.4)
        section.left_margin = Cm(1.4)
        section.right_margin = Cm(1.4)


def _docx_title(document: Document, title: str, subtitle: str = ''):
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = paragraph.add_run(title)
    run.bold = True
    run.font.size = Pt(18)
    if subtitle:
        sub = document.add_paragraph()
        sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = sub.add_run(subtitle)
        r.bold = True
        r.font.size = Pt(10)


def _docx_table(document: Document, headers: list[str], rows: list[list[Any]]):
    table = document.add_table(rows=1, cols=len(headers))
    table.style = 'Table Grid'
    table.autofit = True
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = str(header)
        for run in cell.paragraphs[0].runs:
            run.bold = True
            run.font.size = Pt(8)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = '' if value is None else str(value)
            for paragraph in cells[index].paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(8)
    return table


def _worker_master_data(worker: WorkerProfile) -> dict:
    try:
        return dict(worker.master_data.data or {})
    except Exception:
        master = EmployeeMasterData.objects.filter(worker=worker).first()
        return dict(master.data or {}) if master else {}


def worker_docx(worker: WorkerProfile, queryset) -> bytes:
    rows = list(queryset.select_related('worker__user'))
    statements = _statement_map(rows)
    absences = absence_summary_map(rows)
    master = _worker_master_data(worker)
    document = Document()
    _docx_style(document)
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width

    _docx_title(
        document,
        'Arbeitszeitnachweis und Lohnkonto',
        f'{worker.user} · {master.get("employment_type_lexware") or worker.get_employment_type_display()}',
    )

    info_rows = [
        ['Eintritt', master.get('entry_date') or ''],
        ['Beschäftigung', master.get('employment_type_lexware') or worker.get_employment_type_display()],
        ['Vergütung', 'Gehalt' if master.get('compensation_type') == 'salary' else 'Stundenlohn'],
        ['Stundenlohn', f"{master.get('hourly_rate') or worker.tariff_hourly_rate or ''} €" if master.get('compensation_type') != 'salary' else ''],
        ['Monatsgehalt', f"{master.get('monthly_salary') or ''} €" if master.get('compensation_type') == 'salary' else ''],
        ['Wochenstunden', master.get('weekly_hours') or ''],
        ['Sollstunden monatlich', str(worker.monthly_hours or '')],
    ]
    _docx_table(document, ['Stammdatum', 'Wert'], info_rows)
    document.add_paragraph()

    monthly_rows = []
    for row in rows:
        item = record_dict(
            row,
            statements.get((str(row.worker_id), row.year_month)),
            absence_summary=absences.get((str(row.worker_id), row.year_month)),
        )
        payroll = item.get('payroll_statement') or {}
        monthly_rows.append([
            row.year_month.strftime('%m/%Y'),
            item['ist_hours'],
            item['soll_hours'],
            item['balance_reference_hours'],
            item['monthly_balance_hours'],
            item['saldo_cumulative'],
            f"{item['hourly_rate']} €",
            item['night_hours'],
            item['saturday_hours'],
            item['sunday_hours'],
            f"{item['surcharge_amount']} €",
            item['absence_days'],
            item['vacation_days'],
            item['sick_days'],
            f"{payroll.get('gross_amount') or ''} €" if payroll.get('gross_amount') else '',
            f"{payroll.get('net_amount') or ''} €" if payroll.get('net_amount') else '',
            f"{payroll.get('lexware_payout_amount') or payroll.get('transferred_amount') or ''} €" if (payroll.get('lexware_payout_amount') or payroll.get('transferred_amount')) else '',
        ])
    _docx_table(
        document,
        ['Monat', 'Ist', 'Soll', 'Basis', 'Saldo Monat', 'Saldo gesamt', 'Satz', 'Nacht', 'Sa', 'So', 'Zuschläge', 'Abw.', 'Urlaub', 'Krank', 'Lexware Brutto', 'Lexware Netto', 'Auszahlung'],
        monthly_rows,
    )

    for row in rows:
        entries = sorted(
            list(row.raw_entries or []),
            key=lambda item: str(item.get('local_clock_in') or item.get('clock_in') or ''),
        )
        if not entries:
            continue
        document.add_page_break()
        item = record_dict(
            row,
            statements.get((str(row.worker_id), row.year_month)),
            absence_summary=absences.get((str(row.worker_id), row.year_month)),
        )
        heading = document.add_paragraph()
        run = heading.add_run(row.year_month.strftime('%m/%Y'))
        run.bold = True
        run.font.size = Pt(14)
        document.add_paragraph(
            f"Ist {item['ist_hours']} Std. | Soll {item['soll_hours']} Std. | "
            f"Basis {item['balance_reference_hours']} Std. | Monatssaldo {item['monthly_balance_hours']} Std. | "
            f"Saldo gesamt {item['saldo_cumulative']} Std. | "
            f"Abwesenheit {item['absence_days']} Tage | Urlaub {item['vacation_days']} | Krank {item['sick_days']}"
        )
        daily = []
        for entry in entries:
            client = str(entry.get('client_name') or 'Ohne Zuordnung')
            location = str(entry.get('location_name') or entry.get('position_name') or '')
            daily.append([
                _pdf_date(entry.get('local_clock_in') or entry.get('clock_in')),
                client,
                location,
                f"{_pdf_clock(entry.get('planned_start'))} bis {_pdf_clock(entry.get('planned_end'))}",
                f"{_pdf_clock(entry.get('local_clock_in') or entry.get('clock_in'))} bis {_pdf_clock(entry.get('local_clock_out') or entry.get('clock_out'))}",
                f"{int(entry.get('break_minutes') or 0)} Min.",
                _pdf_hours(entry.get('worked_minutes')),
                _pdf_hours(entry.get('night_minutes')),
                _pdf_hours(entry.get('saturday_minutes')),
                _pdf_hours(entry.get('sunday_minutes')),
            ])
        _docx_table(
            document,
            ['Datum', 'Kunde', 'Ort', 'Plan', 'Ist', 'Pause', 'Netto', 'Nacht', 'Sa', 'So'],
            daily,
        )

    document.add_paragraph()
    note = document.add_paragraph(
        'Hinweis: Ist Zeiten stammen aus der tatsächlichen Zeiterfassung. '
        'Dienstplanzeiten dienen nur dem Vergleich. Lexware Werte werden als eigener Nachweis geführt.'
    )
    note.runs[0].italic = True
    return _docx_bytes(document)


def _supplement_totals(payroll: dict, keyword: str) -> tuple[Decimal | None, Decimal | None]:
    supplements = payroll.get('lexware_supplements') or []
    hours = []
    amounts = []
    for item in supplements:
        if keyword.lower() in str(item.get('label') or '').lower():
            hours.append(dec(item.get('hours')))
            amounts.append(dec(item.get('amount')))
    if not hours:
        return None, None
    return (
        sum(hours, Decimal('0.00')).quantize(TWO),
        sum(amounts, Decimal('0.00')).quantize(TWO),
    )


def _supplement_hours(payroll: dict, keyword: str) -> Decimal | None:
    return _supplement_totals(payroll, keyword)[0]


def _surcharge_reconciliation(item: dict) -> dict:
    payroll = item.get('payroll_statement') or {}
    result = {}
    statuses = []
    mapping = (
        ('night_hours', 'night_surcharge_amount', 'night', 'Nacht', 'nacht'),
        ('saturday_hours', 'saturday_surcharge_amount', 'saturday', 'Samstag', 'samstag'),
        ('sunday_hours', 'sunday_surcharge_amount', 'sunday', 'Sonntag', 'sonntag'),
    )
    for hours_key, amount_key, output_key, label, keyword in mapping:
        app_hours = dec(item.get(hours_key))
        app_amount = dec(item.get(amount_key))
        lexware_hours, lexware_amount = _supplement_totals(payroll, keyword)

        if lexware_hours is None:
            # Time falling into a category is not itself a payroll discrepancy.
            # Only warn when A+ actually expects a monetary supplement.
            status = 'MATCH' if app_amount <= Decimal('0.01') else 'PRÜFEN'
        else:
            hours_match = abs(app_hours - lexware_hours) <= Decimal('0.10')
            amount_match = (
                lexware_amount is None
                or abs(app_amount - lexware_amount) <= Decimal('0.10')
            )
            status = 'MATCH' if hours_match and amount_match else 'ABWEICHUNG'

        statuses.append(status)
        result[output_key] = {
            'label': label,
            'status': status,
            'aplus_hours': str(app_hours),
            'aplus_amount': str(app_amount),
            'lexware_hours': str(lexware_hours) if lexware_hours is not None else None,
            'lexware_amount': str(lexware_amount) if lexware_amount is not None else None,
        }

    result['overall'] = (
        'ABWEICHUNG'
        if 'ABWEICHUNG' in statuses
        else 'PRÜFEN'
        if 'PRÜFEN' in statuses
        else 'MATCH'
    )
    return result


def _reconciliation_status(item: dict) -> tuple[str, list[str]]:
    payroll = item.get('payroll_statement') or {}
    issues = []
    hard_difference = False

    payout = dec(payroll.get('lexware_payout_amount')) if payroll.get('lexware_payout_amount') not in (None, '') else None
    payment_list = dec(payroll.get('transferred_amount')) if payroll.get('transferred_amount') not in (None, '') else None
    if payout is not None and payment_list is not None and abs(payout - payment_list) > Decimal('0.01'):
        hard_difference = True
        issues.append(f'Auszahlung {payout} € ≠ Zahlungsliste {payment_list} €')
    elif payout is None or payment_list is None:
        issues.append('Auszahlung oder Zahlungsliste fehlt')

    if payroll.get('lexware_compensation_type') == 'hourly':
        lex_hours = dec(payroll.get('lexware_paid_hours')) if payroll.get('lexware_paid_hours') not in (None, '') else None
        paid = dec(item.get('paid_total_hours'))
        if lex_hours is not None and abs(lex_hours - paid) > Decimal('0.05'):
            hard_difference = True
            issues.append(f'Bezahlte Stunden {paid} ≠ Lexware {lex_hours}')
        elif lex_hours is None:
            issues.append('Lexware Stunden fehlen')

    for hours_key, amount_key, label, keyword in (
        ('night_hours', 'night_surcharge_amount', 'Nacht', 'nacht'),
        ('saturday_hours', 'saturday_surcharge_amount', 'Samstag', 'samstag'),
        ('sunday_hours', 'sunday_surcharge_amount', 'Sonntag', 'sonntag'),
    ):
        app_hours = dec(item.get(hours_key))
        app_amount = dec(item.get(amount_key))
        lex_hours, lex_amount = _supplement_totals(payroll, keyword)
        if lex_hours is not None:
            if abs(app_hours - lex_hours) > Decimal('0.10'):
                hard_difference = True
                issues.append(f'{label} A+ {app_hours} Std. ≠ Lexware {lex_hours} Std.')
            elif lex_amount is not None and abs(app_amount - lex_amount) > Decimal('0.10'):
                hard_difference = True
                issues.append(f'{label} Zuschlag A+ {app_amount} € ≠ Lexware {lex_amount} €')
        elif app_amount > Decimal('0.01'):
            issues.append(
                f'{label} Zuschlag in A+ {app_amount} €, aber in Lexware nicht nachgewiesen'
            )

    contract_issues = list(item.get('contract_issues') or [])
    if contract_issues:
        issues.extend(issue for issue in contract_issues if issue not in issues)
        if any(issue.startswith('Vergütungsart stimmt nicht') for issue in contract_issues):
            hard_difference = True

    if hard_difference:
        return 'ABWEICHUNG', issues
    if issues:
        return 'PRÜFEN', issues
    return 'MATCH', []


def lexware_reconciliation_docx(queryset, period: date) -> bytes:
    rows = list(queryset.select_related('worker__user'))
    statements = _statement_map(rows)
    document = Document()
    _docx_style(document)
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    _docx_title(document, 'Lexware Abgleich', period.strftime('%m/%Y'))

    table_rows = []
    detail_blocks = []
    for row in rows:
        item = record_dict(row, statements.get((str(row.worker_id), row.year_month)))
        payroll = item.get('payroll_statement') or {}
        status, issues = _reconciliation_status(item)
        master = _worker_master_data(row.worker)
        compensation = (
            f"Gehalt {master.get('monthly_salary') or payroll.get('lexware_monthly_salary') or ''} €"
            if (master.get('compensation_type') == 'salary' or payroll.get('lexware_compensation_type') == 'salary')
            else f"{master.get('hourly_rate') or payroll.get('lexware_hourly_rate') or item.get('hourly_rate') or ''} €/Std."
        )
        table_rows.append([
            item['employee_name'],
            master.get('employment_type_lexware') or item.get('employment_type') or '',
            item['ist_hours'],
            item['soll_hours'],
            item['paid_total_hours'],
            item['monthly_balance_hours'],
            compensation,
            f"{payroll.get('gross_amount') or ''} €" if payroll.get('gross_amount') else '',
            f"{payroll.get('net_amount') or ''} €" if payroll.get('net_amount') else '',
            f"{payroll.get('lexware_payout_amount') or payroll.get('transferred_amount') or ''} €" if (payroll.get('lexware_payout_amount') or payroll.get('transferred_amount')) else '',
            status,
        ])
        if issues:
            detail_blocks.append((item['employee_name'], status, issues))

    _docx_table(
        document,
        ['Mitarbeiter', 'Beschäftigung', 'Ist', 'Soll', 'Bezahlt', 'Saldo', 'Vergütung', 'Brutto', 'Netto', 'Auszahlung', 'Status'],
        table_rows,
    )

    if detail_blocks:
        document.add_paragraph()
        heading = document.add_paragraph()
        r = heading.add_run('Prüfhinweise')
        r.bold = True
        r.font.size = Pt(13)
        for employee, status, issues in detail_blocks:
            paragraph = document.add_paragraph(style='List Bullet')
            paragraph.add_run(f'{employee}: {status}. ').bold = True
            paragraph.add_run('; '.join(issues))

    document.add_paragraph()
    note = document.add_paragraph(
        'Status MATCH bedeutet, dass die vorhandenen Nachweise innerhalb der Toleranz übereinstimmen. '
        'PRÜFEN bedeutet, dass ein Nachweis fehlt. ABWEICHUNG bedeutet, dass vorhandene Werte voneinander abweichen.'
    )
    note.runs[0].italic = True
    return _docx_bytes(document)


def payroll_audit_docx(queryset, year: int, readiness: dict | None = None) -> bytes:
    rows = list(queryset.select_related('worker__user').order_by('worker__user__last_name', 'worker__user__first_name', 'year_month'))
    statements = _statement_map(rows)
    absences = absence_summary_map(rows)

    document = Document()
    _docx_style(document)
    section = document.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    _docx_title(document, 'Prüfbericht Arbeitszeit und Lexware', str(year))

    items = []
    for row in rows:
        items.append(record_dict(
            row,
            statements.get((str(row.worker_id), row.year_month)),
            absence_summary=absences.get((str(row.worker_id), row.year_month)),
        ))

    closed_items = [item for item in items if item.get('reconciliation_status') != 'LAUFEND']
    match_count = sum(1 for item in closed_items if item.get('reconciliation_status') == 'MATCH')
    review_count = sum(1 for item in closed_items if item.get('reconciliation_status') == 'PRÜFEN')
    mismatch_count = sum(1 for item in closed_items if item.get('reconciliation_status') == 'ABWEICHUNG')

    summary_rows = [
        ['Monatskonten', len(items)],
        ['Abgeschlossene Konten', len(closed_items)],
        ['MATCH', match_count],
        ['PRÜFEN', review_count],
        ['ABWEICHUNG', mismatch_count],
    ]
    if readiness:
        summary_rows.extend([
            ['Lexware Kernnachweise', f"{readiness.get('core_documents_present', 0)} / {readiness.get('core_documents_expected', 0)}"],
            ['Vollständige Lexware Monate', f"{readiness.get('complete_months', 0)} / {readiness.get('expected_months', 0)}"],
            ['Jahresnachweise', 'vollständig' if readiness.get('annual_complete') else 'prüfen'],
            ['Weiterer Import nötig', 'Nein' if readiness.get('no_additional_import_required') else 'Ja'],
        ])
    _docx_table(document, ['Prüfung', 'Ergebnis'], summary_rows)

    document.add_paragraph()
    heading = document.add_paragraph()
    run = heading.add_run('Monatsübersicht')
    run.bold = True
    run.font.size = Pt(13)

    overview_rows = []
    for item in items:
        payroll = item.get('payroll_statement') or {}
        overview_rows.append([
            item.get('employee_name') or '',
            item.get('year_month') or '',
            item.get('employment_type') or '',
            item.get('ist_hours') or '0',
            item.get('balance_reference_hours') or '0',
            item.get('monthly_balance_hours') or '0',
            item.get('saldo_cumulative') or '0',
            item.get('vacation_days') or 0,
            item.get('sick_days') or 0,
            payroll.get('gross_amount') or '',
            payroll.get('net_amount') or '',
            payroll.get('lexware_payout_amount') or payroll.get('transferred_amount') or '',
            item.get('reconciliation_status') or '',
        ])
    _docx_table(
        document,
        ['Mitarbeiter', 'Monat', 'Beschäftigung', 'Ist', 'Basis', 'Saldo Monat', 'Saldo gesamt', 'Urlaub', 'Krank', 'Lexware Brutto', 'Lexware Netto', 'Auszahlung', 'Status'],
        overview_rows,
    )

    exceptions = [
        item for item in closed_items
        if item.get('reconciliation_status') in {'PRÜFEN', 'ABWEICHUNG'}
        or item.get('contract_issues')
    ]
    document.add_paragraph()
    heading = document.add_paragraph()
    run = heading.add_run('Offene Prüfpunkte')
    run.bold = True
    run.font.size = Pt(13)
    if not exceptions:
        document.add_paragraph('Keine offenen Prüfpunkte in den abgeschlossenen Monatskonten.')
    else:
        exception_rows = []
        for item in exceptions:
            issues = list(item.get('reconciliation_issues') or [])
            for issue in item.get('contract_issues') or []:
                if issue not in issues:
                    issues.append(issue)
            exception_rows.append([
                item.get('employee_name') or '',
                item.get('year_month') or '',
                item.get('reconciliation_status') or '',
                ' | '.join(issues),
            ])
        _docx_table(document, ['Mitarbeiter', 'Monat', 'Status', 'Prüfhinweise'], exception_rows)

    if readiness:
        document.add_paragraph()
        heading = document.add_paragraph()
        run = heading.add_run('Lexware Datenvollständigkeit')
        run.bold = True
        run.font.size = Pt(13)
        readiness_rows = []
        for item in readiness.get('months') or []:
            docs = item.get('documents') or {}
            readiness_rows.append([
                item.get('period') or '',
                'Ja' if docs.get('lohnabrechnungen') else 'Nein',
                'Ja' if docs.get('zahlungsliste') else 'Nein',
                'Ja' if docs.get('lohnjournal') else 'Nein',
                'Ja' if docs.get('sepa') else 'Nein',
                'Ja' if docs.get('meldebescheinigungen') else 'Nein',
                item.get('statements') or 0,
                'Vollständig' if item.get('core_complete') else 'Prüfen',
            ])
        _docx_table(
            document,
            ['Monat', 'Abrechnung', 'Zahlungsliste', 'Lohnjournal', 'SEPA', 'Meldungen', 'Mitarbeiterkonten', 'Status'],
            readiness_rows,
        )

    note = document.add_paragraph(
        'Hinweis: Ist Zeiten stammen aus der tatsächlichen Zeiterfassung. Dienstplan bleibt Vergleichsdaten. '
        'Bei Stundenlohn wird mit den in Lexware ausgewiesenen bezahlten Stunden abgeglichen. '
        'Bei Gehalt ist die vertragliche Sollzeit die Saldo Basis. Abwesenheiten werden separat ausgewiesen '
        'und verändern den Saldo nicht automatisch.'
    )
    note.runs[0].italic = True
    return _docx_bytes(document)


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
