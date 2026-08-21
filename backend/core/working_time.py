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
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import (
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


def update_record(record: WorkingTimeAccountRecord, *, paid_hours=None, manual_adjustment=None) -> WorkingTimeAccountRecord:
    if paid_hours is not None:
        record.paid_hours = max(Decimal('0'), dec(paid_hours))
    if manual_adjustment is not None:
        record.manual_adjustment = dec(manual_adjustment)
    previous = WorkingTimeAccountRecord.objects.filter(worker=record.worker, year_month__lt=record.year_month).order_by('-year_month').first()
    record.carryover_previous = previous.saldo_cumulative if previous else Decimal('0')
    record.saldo_cumulative = (record.carryover_previous + record.difference_hours + record.manual_adjustment - record.paid_hours).quantize(TWO)
    record.save(update_fields=['paid_hours', 'manual_adjustment', 'carryover_previous', 'saldo_cumulative', 'updated_at'])
    # Recalculate following months so a correction carries forward consistently.
    carry = record.saldo_cumulative
    for row in WorkingTimeAccountRecord.objects.filter(worker=record.worker, year_month__gt=record.year_month).order_by('year_month'):
        row.carryover_previous = carry
        row.saldo_cumulative = (carry + row.difference_hours + row.manual_adjustment - row.paid_hours).quantize(TWO)
        row.save(update_fields=['carryover_previous', 'saldo_cumulative', 'updated_at'])
        carry = row.saldo_cumulative
    return record


def record_dict(row: WorkingTimeAccountRecord) -> dict:
    return {
        'id': str(row.id),
        'worker_id': str(row.worker_id),
        'employee_name': str(row.worker.user),
        'wiw_user_id': row.worker.wiw_user_id,
        'year_month': row.year_month.strftime('%Y-%m'),
        'ist_hours': str(row.ist_hours),
        'soll_hours': str(row.soll_hours),
        'difference_hours': str(row.difference_hours),
        'carryover_previous': str(row.carryover_previous),
        'paid_hours': str(row.paid_hours),
        'manual_adjustment': str(row.manual_adjustment),
        'saldo_cumulative': str(row.saldo_cumulative),
        'hourly_rate': str(row.hourly_rate),
        'gross_amount': str(row.gross_amount),
        'source': row.source,
        'synced_at': row.synced_at.isoformat() if row.synced_at else None,
    }


def settings_rows() -> list[dict]:
    ensure_settings()
    rows = WorkingTimeSetting.objects.select_related('worker__user').order_by('worker__user__last_name', 'worker__user__first_name')
    return [{
        'id': str(item.id),
        'worker_id': str(item.worker_id),
        'wiw_user_id': item.worker.wiw_user_id,
        'employee_name': str(item.worker.user),
        'monthly_limit': str(item.monthly_limit),
        'hourly_rate': str(item.hourly_rate),
        'active': item.active,
        'excluded': item.excluded,
        'notes': item.notes,
    } for item in rows]


def export_csv(queryset) -> HttpResponse:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Mitarbeiter', 'Monat', 'Ist-Stunden', 'Soll-Stunden', 'Plusstunden', 'Übertrag', 'Ausbezahlt', 'Korrektur', 'Saldo', 'Stundensatz', 'Brutto'])
    for row in queryset.select_related('worker__user'):
        writer.writerow([str(row.worker.user), row.year_month.strftime('%Y-%m'), row.ist_hours, row.soll_hours, row.difference_hours, row.carryover_previous, row.paid_hours, row.manual_adjustment, row.saldo_cumulative, row.hourly_rate, row.gross_amount])
    response = HttpResponse('\ufeff' + output.getvalue(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="arbeitszeitkonto.csv"'
    return response


def export_xlsx(queryset) -> HttpResponse:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Arbeitszeitkonto'
    headers = ['Mitarbeiter', 'Monat', 'Ist-Stunden', 'Soll-Stunden', 'Plusstunden', 'Übertrag', 'Ausbezahlt', 'Korrektur', 'Saldo', 'Stundensatz', 'Brutto']
    ws.append(headers)
    for row in queryset.select_related('worker__user'):
        ws.append([str(row.worker.user), row.year_month.strftime('%Y-%m'), float(row.ist_hours), float(row.soll_hours), float(row.difference_hours), float(row.carryover_previous), float(row.paid_hours), float(row.manual_adjustment), float(row.saldo_cumulative), float(row.hourly_rate), float(row.gross_amount)])
    for column in ws.columns:
        ws.column_dimensions[column[0].column_letter].width = min(max(len(str(cell.value or '')) for cell in column) + 2, 32)
    buffer = io.BytesIO()
    wb.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="arbeitszeitkonto.xlsx"'
    return response


def worker_pdf(worker: WorkerProfile, queryset) -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='WTTitle', parent=styles['Title'], alignment=TA_CENTER, spaceAfter=12))
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    story = [Paragraph('Arbeitszeitkonto', styles['WTTitle']), Paragraph(str(worker.user), styles['Heading2']), Spacer(1, 8)]
    data = [['Monat', 'Ist', 'Soll', 'Plus', 'Übertrag', 'Ausbezahlt', 'Korrektur', 'Saldo', 'Brutto']]
    for row in queryset:
        data.append([row.year_month.strftime('%m/%Y'), row.ist_hours, row.soll_hours, row.difference_hours, row.carryover_previous, row.paid_hours, row.manual_adjustment, row.saldo_cumulative, f'{row.gross_amount} €'])
    table = Table(data, repeatRows=1, colWidths=[25 * mm] + [24 * mm] * 8)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#163B65')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#CCD5E0')),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F8FC')]),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(table)
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
