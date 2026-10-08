from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Min, Q
from django.utils import timezone

from .models import (
    EmployeeMasterData,
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


def _effective_local_interval(entry: TimeEntry, current_tz) -> tuple[datetime, datetime, bool]:
    """Return the local payroll interval and whether a one-day rollover was repaired.

    Imported/native attendance can occasionally contain a clock-out date one
    calendar day too late while its clock time still matches the planned shift
    end. We repair only a very strong signal: raw attendance exceeds 18 hours,
    the planned shift is at most 18 hours, and moving the clock-out time back
    one day yields a plausible duration whose end is within six hours of the
    planned end. The source timestamp stays on TimeEntry for audit.
    """
    local_start = timezone.localtime(entry.clock_in, current_tz)
    local_end = timezone.localtime(entry.clock_out, current_tz)
    raw_duration = local_end - local_start

    if entry.shift_id and raw_duration > timedelta(hours=18):
        planned_start = timezone.localtime(entry.shift.starts_at, current_tz)
        planned_end = timezone.localtime(entry.shift.ends_at, current_tz)
        planned_duration = planned_end - planned_start
        if timedelta(0) < planned_duration <= timedelta(hours=18):
            candidate = timezone.make_aware(
                datetime.combine(local_start.date(), local_end.time().replace(tzinfo=None)),
                current_tz,
            )
            if candidate <= local_start:
                candidate += timedelta(days=1)

            planned_candidate_end = timezone.make_aware(
                datetime.combine(local_start.date(), planned_end.time().replace(tzinfo=None)),
                current_tz,
            )
            planned_candidate_start = timezone.make_aware(
                datetime.combine(local_start.date(), planned_start.time().replace(tzinfo=None)),
                current_tz,
            )
            if planned_candidate_end <= planned_candidate_start:
                planned_candidate_end += timedelta(days=1)

            candidate_duration = candidate - local_start
            end_delta = abs(candidate - planned_candidate_end)
            if (
                timedelta(0) < candidate_duration <= timedelta(hours=18)
                and end_delta <= timedelta(hours=6)
            ):
                return local_start, candidate, True

    return local_start, local_end, False


def _entry_metrics(entry: TimeEntry, current_tz) -> dict:
    """Return payroll/audit metrics from the same approved TimeEntry used for IST.

    We do not know the exact position of a break inside the shift. As in the
    existing attendance report, category minutes are therefore reduced
    proportionally by the unpaid break.
    """
    local_start, local_end, corrected_rollover = _effective_local_interval(entry, current_tz)
    gross_minutes = max(0, int((local_end - local_start).total_seconds() // 60))
    worked_minutes = (
        max(0, gross_minutes - int(entry.effective_break_minutes))
        if corrected_rollover
        else max(0, int(entry.worked_minutes))
    )
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
        'clock_out_rollover_corrected': corrected_rollover,
        'effective_local_clock_out': local_end.isoformat(),
    }


def _surcharge_amount(minutes: int, hourly_rate: Decimal, percent: Decimal) -> Decimal:
    if minutes <= 0 or percent <= 0:
        return Decimal('0.00')
    return (
        Decimal(minutes) / Decimal('60') * hourly_rate * percent / Decimal('100')
    ).quantize(TWO)


def sync_working_time(
    start: date,
    end: date,
    *,
    include_inactive_workers: bool = False,
    refresh_contract_terms: bool = False,
    reset_carry: bool = False,
) -> WorkingTimeSyncLog:
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

    master_map = {
        item.worker_id: dict(item.data or {})
        for item in EmployeeMasterData.objects.filter(worker_id__in=[worker.id for worker in workers])
    }

    settings_map = {
        row.worker_id: row
        for row in WorkingTimeSetting.objects.select_related('worker').all()
    }
    # Closed entries define when an employee first has an attendance month.
    # Approval controls whether those minutes count toward IST, not whether the
    # month exists at all. This preserves the existing review workflow where an
    # unapproved closed entry yields a zero-IST monthly record until approval.
    history_bounds = {
        row['worker_id']: row
        for row in (
            TimeEntry.objects
            .filter(clock_out__isnull=False)
            .values('worker_id')
            .annotate(first_clock_in=Min('clock_in'), last_clock_out=Max('clock_out'))
        )
    }

    grouped = defaultdict(list)
    hours_by_key = defaultdict(lambda: Decimal('0'))

    # A month only belongs to the working-time account when there is at least
    # one closed attendance row for that employee. Older rebuild logic filled
    # every calendar month between first and last attendance with zero IST,
    # which created artificial negative cumulative balances for gaps where no
    # authoritative attendance data existed.
    closed_month_keys = {
        (
            entry.worker_id,
            timezone.localtime(entry.clock_in, current_tz).date().replace(day=1),
        )
        for entry in closed_entries
    }

    for entry in approved_entries:
        local_clock_in = timezone.localtime(entry.clock_in, current_tz)
        metrics = _entry_metrics(entry, current_tz)
        local_clock_out = datetime.fromisoformat(metrics['effective_local_clock_out'])
        month = local_clock_in.date().replace(day=1)
        key = (str(entry.worker_id), month)
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
            'source_clock_out': entry.clock_out.isoformat(),
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
            master_data = master_map.get(worker.id, {})
            compensation_type = str(master_data.get('compensation_type') or '').strip().lower()
            is_salary = compensation_type == 'salary'
            monthly_salary = dec(master_data.get('monthly_salary')) if master_data.get('monthly_salary') not in (None, '') else None
            night_percent = dec(row_setting.night_surcharge_percent if row_setting else 0)
            saturday_percent = dec(row_setting.saturday_surcharge_percent if row_setting else 0)
            sunday_percent = dec(row_setting.sunday_surcharge_percent if row_setting else 0)

            worker_months = sorted(
                month
                for worker_id, month in closed_month_keys
                if worker_id == worker.id
                and worker_range_start <= month <= worker_range_end
            )
            if not worker_months:
                continue

            # Remove only stale auto-generated account rows in the rebuild
            # window. Manual/payroll evidence is untouched. A closed but still
            # unapproved attendance row remains valid because its month is in
            # worker_months and will intentionally show zero IST until approval.
            (
                WorkingTimeAccountRecord.objects
                .filter(
                    worker=worker,
                    year_month__gte=worker_range_start,
                    year_month__lte=worker_range_end,
                    source='aplus_time_entries',
                )
                .exclude(year_month__in=worker_months)
                .delete()
            )

            first_rebuilt_month = worker_months[0]
            prior = None
            if not reset_carry:
                prior = (
                    WorkingTimeAccountRecord.objects
                    .filter(worker=worker, year_month__lt=first_rebuilt_month)
                    .order_by('-year_month')
                    .first()
                )
            carry = prior.saldo_cumulative if prior else Decimal('0.00')

            current_month = timezone.localdate().replace(day=1)
            for month in worker_months:
                existing = WorkingTimeAccountRecord.objects.filter(
                    worker=worker,
                    year_month=month,
                ).first()
                closed_month = month < current_month

                month_limit = (
                    monthly_limit
                    if refresh_contract_terms
                    else (
                        dec(existing.soll_hours)
                        if existing and closed_month
                        else monthly_limit
                    )
                )
                month_rate = (
                    dec(existing.hourly_rate)
                    if existing and closed_month and dec(existing.hourly_rate) > 0
                    else effective_rate
                )
                employment_snapshot = (
                    worker.employment_type
                    if refresh_contract_terms
                    else (
                        existing.employment_type_snapshot
                        if existing and existing.employment_type_snapshot
                        else worker.employment_type
                    )
                )

                ist = hours_by_key.get((str(worker.id), month), Decimal('0')).quantize(TWO)
                difference = (ist - month_limit).quantize(TWO)
                legacy_paid_extra = existing.paid_hours if existing else Decimal('0')
                if is_salary:
                    paid_total = (
                        existing.paid_total_hours
                        if existing and existing.paid_total_hours is not None
                        else Decimal('0.00')
                    ).quantize(TWO)
                    balance_reference = month_limit
                else:
                    paid_total = (
                        existing.paid_total_hours
                        if existing and existing.paid_total_hours is not None
                        else (month_limit + legacy_paid_extra)
                    ).quantize(TWO)
                    balance_reference = paid_total
                manual = existing.manual_adjustment if existing else Decimal('0')
                saldo = (carry + ist + manual - balance_reference).quantize(TWO)
                gross = (
                    monthly_salary.quantize(TWO)
                    if is_salary and monthly_salary is not None
                    else (ist * month_rate).quantize(TWO)
                )

                raw_entries = grouped.get((str(worker.id), month), [])
                previous_raw = {
                    str(item.get('id')): item
                    for item in (existing.raw_entries if existing and closed_month else []) or []
                    if item.get('id')
                }
                for raw in raw_entries:
                    previous = previous_raw.get(str(raw.get('id'))) or {}
                    if refresh_contract_terms:
                        row_night_percent = night_percent
                        row_saturday_percent = saturday_percent
                        row_sunday_percent = sunday_percent
                    else:
                        row_night_percent = dec(previous.get('night_surcharge_percent', night_percent))
                        row_saturday_percent = dec(previous.get('saturday_surcharge_percent', saturday_percent))
                        row_sunday_percent = dec(previous.get('sunday_surcharge_percent', sunday_percent))
                    raw['night_surcharge_percent'] = str(row_night_percent)
                    raw['saturday_surcharge_percent'] = str(row_saturday_percent)
                    raw['sunday_surcharge_percent'] = str(row_sunday_percent)
                    raw['night_surcharge_amount'] = str(_surcharge_amount(raw['night_minutes'], month_rate, row_night_percent))
                    raw['saturday_surcharge_amount'] = str(_surcharge_amount(raw['saturday_minutes'], month_rate, row_saturday_percent))
                    raw['sunday_surcharge_amount'] = str(_surcharge_amount(raw['sunday_minutes'], month_rate, row_sunday_percent))

                WorkingTimeAccountRecord.objects.update_or_create(
                    worker=worker,
                    year_month=month,
                    defaults={
                        'ist_hours': ist,
                        'soll_hours': month_limit,
                        'difference_hours': difference,
                        'carryover_previous': carry,
                        'paid_hours': legacy_paid_extra,
                        'paid_total_hours': paid_total,
                        'employment_type_snapshot': employment_snapshot,
                        'manual_adjustment': manual,
                        'saldo_cumulative': saldo,
                        'hourly_rate': month_rate,
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
                'refresh_contract_terms': refresh_contract_terms,
                'include_inactive_workers': include_inactive_workers,
                'reset_carry': reset_carry,
            },
        )

    return log
