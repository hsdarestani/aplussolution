from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Min, Q
from django.utils import timezone

from .models import (
    TimeEntry,
    WorkerProfile,
    WorkingTimeAccountRecord,
    WorkingTimeSetting,
    WorkingTimeSyncLog,
)
from .working_time import dec, ensure_settings, iter_months

TWO = Decimal('0.01')


def effective_hourly_rate(worker: WorkerProfile, row_setting: WorkingTimeSetting | None = None) -> tuple[Decimal, Decimal, Decimal]:
    """Return (base rate, allowance, effective rate) for payroll preparation."""
    base = dec(
        (row_setting.hourly_rate if row_setting else None)
        or worker.tariff_hourly_rate
        or settings.WORKING_TIME_DEFAULT_HOURLY_RATE
    )
    allowance = dec(worker.extra_allowance or 0)
    return base, allowance, (base + allowance).quantize(TWO)


def _overlap_minutes(start: datetime, end: datetime, window_start: datetime, window_end: datetime) -> int:
    overlap_start = max(start, window_start)
    overlap_end = min(end, window_end)
    if overlap_end <= overlap_start:
        return 0
    return max(0, int((overlap_end - overlap_start).total_seconds() // 60))


def _entry_metrics(entry: TimeEntry, current_tz) -> dict:
    """Return payroll/audit metrics from the same approved TimeEntry used for IST.

    We do not know the exact position of a break inside the shift. As in the
    existing attendance report, category minutes are therefore reduced
    proportionally by the unpaid break.
    """
    local_start = timezone.localtime(entry.clock_in, current_tz)
    local_end = timezone.localtime(entry.clock_out, current_tz)
    gross_minutes = max(0, int((local_end - local_start).total_seconds() // 60))
    worked_minutes = max(0, int(entry.worked_minutes))
    factor = (Decimal(worked_minutes) / Decimal(gross_minutes)) if gross_minutes else Decimal('0')

    night_gross = 0
    saturday_gross = 0
    sunday_gross = 0
    cursor = local_start.date() - timedelta(days=1)
    final_day = local_end.date()
    while cursor <= final_day:
        night_start = timezone.make_aware(datetime.combine(cursor, time(23, 0)), current_tz)
        night_end = timezone.make_aware(datetime.combine(cursor + timedelta(days=1), time(6, 0)), current_tz)
        night_gross += _overlap_minutes(local_start, local_end, night_start, night_end)

        day_start = timezone.make_aware(datetime.combine(cursor, time.min), current_tz)
        day_end = timezone.make_aware(datetime.combine(cursor + timedelta(days=1), time.min), current_tz)
        if cursor.weekday() == 5:
            saturday_gross += _overlap_minutes(local_start, local_end, day_start, day_end)
        if cursor.weekday() == 6:
            sunday_gross += _overlap_minutes(local_start, local_end, day_start, day_end)
        cursor += timedelta(days=1)

    return {
        'gross_minutes': gross_minutes,
        'break_minutes': int(entry.effective_break_minutes),
        'worked_minutes': worked_minutes,
        'night_minutes': int((Decimal(night_gross) * factor).quantize(Decimal('1'))),
        'saturday_minutes': int((Decimal(saturday_gross) * factor).quantize(Decimal('1'))),
        'sunday_minutes': int((Decimal(sunday_gross) * factor).quantize(Decimal('1'))),
    }


def _surcharge_amount(minutes: int, hourly_rate: Decimal, percent: Decimal) -> Decimal:
    if minutes <= 0 or percent <= 0:
        return Decimal('0.00')
    return (
        Decimal(minutes) / Decimal('60') * hourly_rate * percent / Decimal('100')
    ).quantize(TWO)


def sync_working_time(start: date, end: date, *, include_inactive_workers: bool = False) -> WorkingTimeSyncLog:
    """Rebuild payroll records from actual A+ attendance.

    Approved native A+ entries and imported historical WIW time rows are
    authoritative. Planned Shift.start/end values remain comparison data only.
    """
    if end < start:
        raise ValueError('Das Enddatum muss nach dem Startdatum liegen.')

    ensure_settings()
    current_tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start, time.min), current_tz)
    end_dt = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), current_tz)

    closed_entries = list(
        TimeEntry.objects.filter(
            clock_in__gte=start_dt,
            clock_in__lt=end_dt,
            clock_out__isnull=False,
        )
        .select_related('worker__user', 'shift__client', 'shift__location', 'shift__position')
        .order_by('clock_in')
    )

    approved_entries = [
        entry for entry in closed_entries
        if entry.approved or bool(entry.wiw_time_id)
    ]
    excluded_unapproved = len([
        entry for entry in closed_entries
        if not entry.approved and not entry.wiw_time_id
    ])

    worker_queryset = WorkerProfile.objects.select_related('user')
    if not include_inactive_workers:
        worker_queryset = worker_queryset.filter(active=True)
    workers = list(worker_queryset)

    settings_map = {
        row.worker_id: row
        for row in WorkingTimeSetting.objects.select_related('worker').all()
    }
    history_bounds = {
        row['worker_id']: row
        for row in (
            TimeEntry.objects
            .filter(clock_out__isnull=False)
            .filter(Q(approved=True) | (Q(wiw_time_id__isnull=False) & ~Q(wiw_time_id='')))
            .values('worker_id')
            .annotate(first_clock_in=Min('clock_in'), last_clock_out=Max('clock_out'))
        )
    }

    grouped = defaultdict(list)
    hours_by_key = defaultdict(lambda: Decimal('0'))

    for entry in approved_entries:
        local_clock_in = timezone.localtime(entry.clock_in, current_tz)
        local_clock_out = timezone.localtime(entry.clock_out, current_tz)
        month = local_clock_in.date().replace(day=1)
        key = (str(entry.worker_id), month)
        metrics = _entry_metrics(entry, current_tz)
        hours_by_key[key] += Decimal(metrics['worked_minutes']) / Decimal('60')
        shift = entry.shift
        grouped[key].append({
            'id': str(entry.id),
            'worker_id': str(entry.worker_id),
            'shift_id': str(entry.shift_id) if entry.shift_id else None,
            'client_id': str(shift.client_id) if shift else None,
            'client_name': shift.client.name if shift else '',
            'location_id': str(shift.location_id) if shift else None,
            'location_name': shift.location.name if shift else '',
            'position_name': shift.position.name if shift else '',
            'planned_start': shift.starts_at.isoformat() if shift else None,
            'planned_end': shift.ends_at.isoformat() if shift else None,
            'planned_break_minutes': int(shift.break_minutes) if shift else 0,
            'clock_in': entry.clock_in.isoformat(),
            'clock_out': entry.clock_out.isoformat(),
            'local_clock_in': local_clock_in.isoformat(),
            'local_clock_out': local_clock_out.isoformat(),
            **metrics,
            'approved': bool(entry.approved),
            'source': 'wiw_historical' if entry.wiw_time_id else 'aplus',
        })

    now = timezone.now()
    count = 0
    with transaction.atomic():
        for worker in workers:
            row_setting = settings_map.get(worker.id)
            if row_setting and row_setting.excluded:
                continue
            if row_setting and not row_setting.active and not include_inactive_workers:
                continue

            bounds = history_bounds.get(worker.id)
            if not bounds or not bounds.get('first_clock_in'):
                continue
            first_month = timezone.localtime(bounds['first_clock_in'], current_tz).date().replace(day=1)
            last_month = timezone.localtime(bounds['last_clock_out'], current_tz).date().replace(day=1)
            worker_range_start = max(start.replace(day=1), first_month)
            worker_range_end = end
            if include_inactive_workers and not worker.active:
                worker_range_end = min(worker_range_end, last_month)
            if worker_range_end < worker_range_start:
                continue

            monthly_limit = dec(
                (row_setting.monthly_limit if row_setting else None)
                or worker.monthly_hours
                or settings.WORKING_TIME_DEFAULT_MONTHLY_LIMIT
            )
            _base_rate, _allowance, effective_rate = effective_hourly_rate(worker, row_setting)
            night_percent = dec(row_setting.night_surcharge_percent if row_setting else 0)
            saturday_percent = dec(row_setting.saturday_surcharge_percent if row_setting else 0)
            sunday_percent = dec(row_setting.sunday_surcharge_percent if row_setting else 0)

            prior = (
                WorkingTimeAccountRecord.objects
                .filter(worker=worker, year_month__lt=worker_range_start)
                .order_by('-year_month')
                .first()
            )
            carry = prior.saldo_cumulative if prior else Decimal('0.00')

            for month in iter_months(worker_range_start, worker_range_end):
                existing = WorkingTimeAccountRecord.objects.filter(
                    worker=worker,
                    year_month=month,
                ).first()
                ist = hours_by_key.get((str(worker.id), month), Decimal('0')).quantize(TWO)
                difference = (ist - monthly_limit).quantize(TWO)
                legacy_paid_extra = existing.paid_hours if existing else Decimal('0')
                paid_total = (
                    existing.paid_total_hours
                    if existing and existing.paid_total_hours is not None
                    else (monthly_limit + legacy_paid_extra)
                ).quantize(TWO)
                manual = existing.manual_adjustment if existing else Decimal('0')
                # The hour balance is independent from SOLL: actual worked hours
                # minus total compensated hours, plus manual corrections.
                saldo = (carry + ist + manual - paid_total).quantize(TWO)
                gross = (ist * effective_rate).quantize(TWO)

                raw_entries = grouped.get((str(worker.id), month), [])
                for raw in raw_entries:
                    raw['night_surcharge_percent'] = str(night_percent)
                    raw['saturday_surcharge_percent'] = str(saturday_percent)
                    raw['sunday_surcharge_percent'] = str(sunday_percent)
                    raw['night_surcharge_amount'] = str(_surcharge_amount(raw['night_minutes'], effective_rate, night_percent))
                    raw['saturday_surcharge_amount'] = str(_surcharge_amount(raw['saturday_minutes'], effective_rate, saturday_percent))
                    raw['sunday_surcharge_amount'] = str(_surcharge_amount(raw['sunday_minutes'], effective_rate, sunday_percent))

                WorkingTimeAccountRecord.objects.update_or_create(
                    worker=worker,
                    year_month=month,
                    defaults={
                        'ist_hours': ist,
                        'soll_hours': monthly_limit,
                        'difference_hours': difference,
                        'carryover_previous': carry,
                        'paid_hours': legacy_paid_extra,
                        'paid_total_hours': paid_total,
                        'manual_adjustment': manual,
                        'saldo_cumulative': saldo,
                        'hourly_rate': effective_rate,
                        'gross_amount': gross,
                        'raw_entries': raw_entries,
                        'source': 'aplus_time_entries',
                        'synced_at': now,
                    },
                )
                carry = saldo
                count += 1

        message = ''
        status = 'ok'
        if excluded_unapproved:
            status = 'warning'
            message = (
                f'{excluded_unapproved} noch nicht freigegebene A+ Zeiteinträge wurden '
                'aus der Lohnvorbereitung ausgeschlossen.'
            )

        log = WorkingTimeSyncLog.objects.create(
            range_start=start,
            range_end=end,
            status=status,
            message=message,
            records_count=count,
            metadata={
                'source': 'aplus_time_entries',
                'closed_entries': len(closed_entries),
                'approved_entries': len(approved_entries),
                'approved_or_historical_entries': len(approved_entries),
                'excluded_unapproved_entries': excluded_unapproved,
                'include_inactive_workers': include_inactive_workers,
            },
        )

    return log
