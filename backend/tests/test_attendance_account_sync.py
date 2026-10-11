"""A+ attendance lifecycle keeps employee monthly ledgers consistent."""
from datetime import date, datetime
from decimal import Decimal

import pytest
from django.db import transaction
from django.utils import timezone

from core.attendance_account_sync import batch_attendance_changes
from core.models import TimeEntry, WorkingTimeAccountRecord


def local_dt(day, hour, minute=0, month=9):
    return timezone.make_aware(
        datetime(2026, month, day, hour, minute),
        timezone.get_current_timezone(),
    )


@pytest.mark.django_db(transaction=True)
def test_approved_entry_refreshes_monthly_ledger_and_preserves_paid_fields(worker_user):
    worker = worker_user.worker_profile
    first = TimeEntry.objects.create(
        worker=worker, clock_in=local_dt(1, 9),
        clock_out=local_dt(1, 14), approved=True, break_minutes=0,
    )
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=date(2026, 9, 1))
    assert record.source == 'aplus_time_entries'
    assert record.ist_hours == Decimal('5.00')
    assert [row['id'] for row in record.raw_entries] == [str(first.id)]

    record.manual_adjustment = Decimal('1.50')
    record.paid_total_hours = Decimal('3.00')
    record.save(update_fields=['manual_adjustment', 'paid_total_hours'])
    pending = TimeEntry.objects.create(
        worker=worker, clock_in=local_dt(16, 15, 30),
        clock_out=local_dt(16, 21), approved=False, break_minutes=0,
    )
    record.refresh_from_db()
    assert len(record.raw_entries) == 1
    pending.approved = True
    pending.save(update_fields=['approved', 'updated_at'])
    record.refresh_from_db()
    assert record.ist_hours == Decimal('10.50')
    assert len(record.raw_entries) == 2
    assert record.manual_adjustment == Decimal('1.50')
    assert record.paid_total_hours == Decimal('3.00')
    assert record.saldo_cumulative == Decimal('9.00')


@pytest.mark.django_db(transaction=True)
def test_moved_or_deleted_entry_removes_stale_monthly_hours(worker_user):
    worker = worker_user.worker_profile
    entry = TimeEntry.objects.create(
        worker=worker, clock_in=local_dt(16, 15, 30),
        clock_out=local_dt(16, 21), approved=True, break_minutes=0,
    )
    assert WorkingTimeAccountRecord.objects.get(
        worker=worker, year_month=date(2026, 9, 1)
    ).ist_hours == Decimal('5.50')
    entry.clock_in = local_dt(1, 9, month=10)
    entry.clock_out = local_dt(1, 12, month=10)
    entry.save(update_fields=['clock_in', 'clock_out', 'updated_at'])
    sep = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=date(2026, 9, 1))
    oct = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=date(2026, 10, 1))
    assert sep.ist_hours == Decimal('0.00')
    assert sep.raw_entries == []
    assert oct.ist_hours == Decimal('3.00')
    entry.delete()
    oct.refresh_from_db()
    assert oct.ist_hours == Decimal('0.00')
    assert oct.raw_entries == []


@pytest.mark.django_db(transaction=True)
def test_many_imported_rows_are_batched_and_historical_wiw_is_counted(worker_user):
    worker = worker_user.worker_profile
    with transaction.atomic():
        with batch_attendance_changes():
            for day in (1, 3, 9):
                TimeEntry.objects.create(
                    worker=worker,
                    clock_in=local_dt(day, 10),
                    clock_out=local_dt(day, 12),
                    wiw_time_id=f'wiw-row-{day}',
                    approved=False,
                    break_minutes=0,
                )
        assert not WorkingTimeAccountRecord.objects.filter(
            worker=worker, year_month=date(2026, 9, 1)
        ).exists()
    result = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=date(2026, 9, 1))
    assert result.ist_hours == Decimal('6.00')
    assert len(result.raw_entries) == 3


@pytest.mark.django_db(transaction=True)
def test_imported_legacy_month_is_never_overwritten_by_auto_refresh(worker_user):
    worker = worker_user.worker_profile
    legacy = WorkingTimeAccountRecord.objects.create(
        worker=worker, year_month=date(2026, 9, 1),
        source='wiw_times', ist_hours=Decimal('12.00'),
        raw_entries=[{'id': 'historical-evidence', 'worked_minutes': 720}],
    )
    TimeEntry.objects.create(
        worker=worker, clock_in=local_dt(16, 15),
        clock_out=local_dt(16, 21), approved=True,
    )
    legacy.refresh_from_db()
    assert legacy.source == 'wiw_times'
    assert legacy.ist_hours == Decimal('12.00')
    assert legacy.raw_entries[0]['id'] == 'historical-evidence'


@pytest.mark.django_db(transaction=True)
def test_shift_break_change_refreshes_dependent_attendance_hours(worker_user, shift):
    worker = worker_user.worker_profile
    shift.starts_at = local_dt(16, 15)
    shift.ends_at = local_dt(16, 21)
    shift.break_minutes = 0
    shift.save(update_fields=['starts_at', 'ends_at', 'break_minutes', 'updated_at'])
    TimeEntry.objects.create(
        worker=worker, shift=shift,
        clock_in=local_dt(16, 15), clock_out=local_dt(16, 21),
        approved=True, break_minutes=None,
    )
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=date(2026, 9, 1))
    assert record.ist_hours == Decimal('6.00')
    shift.break_minutes = 30
    shift.save(update_fields=['break_minutes', 'updated_at'])
    record.refresh_from_db()
    assert record.ist_hours == Decimal('5.50')
    assert record.raw_entries[0]['break_minutes'] == 30
