from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import Shift, TimeEntry, WorkingTimeAccountRecord, WorkingTimeSetting
from core.native_cutover import sync_working_time
from core.payroll_engine import effective_hourly_rate


@pytest.mark.django_db
def test_payroll_excludes_unapproved_time_and_includes_allowance(
    worker_user, company, location, position
):
    worker = worker_user.worker_profile
    worker.monthly_hours = Decimal('10.00')
    worker.tariff_hourly_rate = Decimal('15.50')
    worker.extra_allowance = Decimal('2.00')
    worker.save(update_fields=[
        'monthly_hours', 'tariff_hourly_rate', 'extra_allowance', 'updated_at'
    ])

    today = timezone.localdate()
    start = timezone.make_aware(
        datetime.combine(today, time(8, 0)), timezone.get_current_timezone()
    )
    approved_shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker,
        starts_at=start,
        ends_at=start + timedelta(hours=8),
        break_minutes=0,
        status=Shift.Status.CONFIRMED,
    )
    unapproved_shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker,
        starts_at=start + timedelta(hours=10),
        ends_at=start + timedelta(hours=14),
        break_minutes=0,
        status=Shift.Status.CONFIRMED,
    )
    TimeEntry.objects.create(
        worker=worker,
        shift=approved_shift,
        clock_in=start,
        clock_out=start + timedelta(hours=8),
        approved=True,
    )
    TimeEntry.objects.create(
        worker=worker,
        shift=unapproved_shift,
        clock_in=start + timedelta(hours=10),
        clock_out=start + timedelta(hours=14),
        approved=False,
    )

    log = sync_working_time(today, today)
    record = WorkingTimeAccountRecord.objects.get(
        worker=worker,
        year_month=today.replace(day=1),
    )

    assert record.ist_hours == Decimal('8.00')
    assert record.soll_hours == Decimal('10.00')
    assert record.difference_hours == Decimal('-2.00')
    assert record.hourly_rate == Decimal('17.50')
    assert record.gross_amount == Decimal('140.00')
    assert len(record.raw_entries) == 1
    assert record.raw_entries[0]['approved'] is True
    assert record.source == 'aplus_time_entries_approved'

    assert log.status == 'warning'
    assert log.metadata['closed_entries'] == 2
    assert log.metadata['approved_entries'] == 1
    assert log.metadata['excluded_unapproved_entries'] == 1
    assert 'aus der Lohnvorbereitung ausgeschlossen' in log.message


@pytest.mark.django_db
def test_payroll_includes_entry_after_manager_approval(
    worker_user, company, location, position
):
    worker = worker_user.worker_profile
    worker.monthly_hours = Decimal('8.00')
    worker.tariff_hourly_rate = Decimal('20.00')
    worker.save(update_fields=['monthly_hours', 'tariff_hourly_rate', 'updated_at'])

    today = timezone.localdate()
    start = timezone.make_aware(
        datetime.combine(today, time(9, 0)), timezone.get_current_timezone()
    )
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker,
        starts_at=start,
        ends_at=start + timedelta(hours=4),
        break_minutes=0,
        status=Shift.Status.CONFIRMED,
    )
    entry = TimeEntry.objects.create(
        worker=worker,
        shift=shift,
        clock_in=start,
        clock_out=start + timedelta(hours=4),
        approved=False,
    )

    sync_working_time(today, today)
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=today.replace(day=1))
    assert record.ist_hours == Decimal('0.00')
    assert record.gross_amount == Decimal('0.00')

    entry.approved = True
    entry.save(update_fields=['approved', 'updated_at'])
    sync_working_time(today, today)
    record.refresh_from_db()
    assert record.ist_hours == Decimal('4.00')
    assert record.gross_amount == Decimal('80.00')


@pytest.mark.django_db
def test_payroll_setting_is_base_rate_and_allowance_is_added(worker_user):
    worker = worker_user.worker_profile
    worker.tariff_hourly_rate = Decimal('15.00')
    worker.extra_allowance = Decimal('2.50')
    worker.save(update_fields=['tariff_hourly_rate', 'extra_allowance', 'updated_at'])
    setting = WorkingTimeSetting.objects.create(
        worker=worker,
        monthly_limit=Decimal('80.00'),
        hourly_rate=Decimal('18.00'),
        active=True,
    )

    base, allowance, effective = effective_hourly_rate(worker, setting)
    assert base == Decimal('18.00')
    assert allowance == Decimal('2.50')
    assert effective == Decimal('20.50')
