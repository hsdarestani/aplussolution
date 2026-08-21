from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
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
    """Return (base rate, allowance, effective rate) for payroll preparation.

    WorkingTimeSetting.hourly_rate is treated as the employee's configurable base
    hourly rate. WorkerProfile.extra_allowance is added consistently on top, the
    same way the labor-cost forecast treats the allowance.
    """
    base = dec(
        (row_setting.hourly_rate if row_setting else None)
        or worker.tariff_hourly_rate
        or settings.WORKING_TIME_DEFAULT_HOURLY_RATE
    )
    allowance = dec(worker.extra_allowance or 0)
    return base, allowance, (base + allowance).quantize(TWO)


def sync_working_time(start: date, end: date) -> WorkingTimeSyncLog:
    """Rebuild payroll-preparation records from approved local A+ time entries only."""
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
        .select_related('worker__user', 'shift')
        .order_by('clock_in')
    )

    approved_entries = [entry for entry in closed_entries if entry.approved]
    excluded_unapproved = len(closed_entries) - len(approved_entries)

    workers = list(WorkerProfile.objects.select_related('user').filter(active=True))
    settings_map = {
        row.worker_id: row
        for row in WorkingTimeSetting.objects.select_related('worker').all()
    }

    grouped = defaultdict(list)
    hours_by_key = defaultdict(lambda: Decimal('0'))

    for entry in approved_entries:
        local_clock_in = timezone.localtime(entry.clock_in, current_tz)
        month = local_clock_in.date().replace(day=1)
        key = (str(entry.worker_id), month)
        worked_minutes = entry.worked_minutes
        hours_by_key[key] += Decimal(worked_minutes) / Decimal('60')
        grouped[key].append({
            'id': str(entry.id),
            'worker_id': str(entry.worker_id),
            'shift_id': str(entry.shift_id) if entry.shift_id else None,
            'clock_in': entry.clock_in.isoformat(),
            'clock_out': entry.clock_out.isoformat() if entry.clock_out else None,
            'worked_minutes': worked_minutes,
            'approved': True,
            'source': 'aplus',
        })

    now = timezone.now()
    count = 0
    with transaction.atomic():
        for worker in workers:
            row_setting = settings_map.get(worker.id)
            if row_setting and (not row_setting.active or row_setting.excluded):
                continue

            monthly_limit = dec(
                (row_setting.monthly_limit if row_setting else None)
                or worker.monthly_hours
                or settings.WORKING_TIME_DEFAULT_MONTHLY_LIMIT
            )
            base_rate, allowance, effective_rate = effective_hourly_rate(worker, row_setting)

            prior = (
                WorkingTimeAccountRecord.objects
                .filter(worker=worker, year_month__lt=start.replace(day=1))
                .order_by('-year_month')
                .first()
            )
            carry = prior.saldo_cumulative if prior else Decimal('0.00')

            for month in iter_months(start, end):
                existing = WorkingTimeAccountRecord.objects.filter(
                    worker=worker,
                    year_month=month,
                ).first()
                ist = hours_by_key.get((str(worker.id), month), Decimal('0')).quantize(TWO)
                difference = (ist - monthly_limit).quantize(TWO)
                paid = existing.paid_hours if existing else Decimal('0')
                manual = existing.manual_adjustment if existing else Decimal('0')
                saldo = (carry + difference + manual - paid).quantize(TWO)
                gross = (ist * effective_rate).quantize(TWO)

                raw_entries = grouped.get((str(worker.id), month), [])
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
                        # Store the effective rate used for this payroll snapshot.
                        'hourly_rate': effective_rate,
                        'gross_amount': gross,
                        'raw_entries': raw_entries,
                        'source': 'aplus_time_entries_approved',
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
                f'{excluded_unapproved} noch nicht freigegebene Zeiteinträge wurden '
                'aus der Lohnvorbereitung ausgeschlossen.'
            )

        log = WorkingTimeSyncLog.objects.create(
            range_start=start,
            range_end=end,
            status=status,
            message=message,
            records_count=count,
            metadata={
                'source': 'aplus_time_entries_approved',
                'closed_entries': len(closed_entries),
                'approved_entries': len(approved_entries),
                'excluded_unapproved_entries': excluded_unapproved,
            },
        )

    return log
