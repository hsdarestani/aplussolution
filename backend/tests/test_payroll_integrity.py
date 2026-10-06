from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.models import PayrollStatement, Shift, TimeEntry, WorkingTimeAccountRecord, WorkingTimeSetting
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
    assert record.source == 'aplus_time_entries'

    assert log.status == 'warning'
    assert log.metadata['source'] == 'aplus_time_entries'
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



@pytest.mark.django_db
def test_fifty_worked_thirty_eight_paid_leaves_twelve_hours_credit(
    auth_admin, worker_user, company, location, position
):
    worker = worker_user.worker_profile
    worker.monthly_hours = Decimal('38.00')
    worker.tariff_hourly_rate = Decimal('15.00')
    worker.save(update_fields=['monthly_hours', 'tariff_hourly_rate', 'updated_at'])

    month = timezone.localdate().replace(day=1)
    tz = timezone.get_current_timezone()
    for offset in range(5):
        actual_start = timezone.make_aware(
            datetime.combine(month + timedelta(days=offset), time(8, 0)), tz
        )
        shift = Shift.objects.create(
            client=company,
            location=location,
            position=position,
            worker=worker,
            # The plan is intentionally only eight hours; actual attendance is ten.
            starts_at=actual_start,
            ends_at=actual_start + timedelta(hours=8),
            break_minutes=0,
            status=Shift.Status.CONFIRMED,
        )
        TimeEntry.objects.create(
            worker=worker,
            shift=shift,
            clock_in=actual_start,
            clock_out=actual_start + timedelta(hours=10),
            break_minutes=0,
            approved=True,
        )

    sync_working_time(month, month + timedelta(days=6))
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=month)

    assert record.ist_hours == Decimal('50.00')
    assert record.soll_hours == Decimal('38.00')
    assert record.paid_total_hours == Decimal('38.00')
    assert record.saldo_cumulative == Decimal('12.00')
    assert len(record.raw_entries) == 5
    assert all(item['client_name'] == company.name for item in record.raw_entries)
    assert all(item['worked_minutes'] == 600 for item in record.raw_entries)
    assert all(item['planned_end'] != item['clock_out'] for item in record.raw_entries)

    response = auth_admin.patch(
        f'/api/working-time/records/{record.id}/',
        {'paid_total_hours': '45.00'},
        format='json',
    )
    assert response.status_code == 200
    record.refresh_from_db()
    assert record.paid_total_hours == Decimal('45.00')
    assert record.saldo_cumulative == Decimal('5.00')


@pytest.mark.django_db
def test_historical_wiw_time_is_authoritative_even_without_native_approval(
    worker_user, company, location, position
):
    worker = worker_user.worker_profile
    worker.monthly_hours = Decimal('8.00')
    worker.save(update_fields=['monthly_hours', 'updated_at'])

    day = timezone.localdate().replace(day=1)
    start = timezone.make_aware(
        datetime.combine(day, time(22, 0)), timezone.get_current_timezone()
    )
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker,
        starts_at=start,
        ends_at=start + timedelta(hours=8),
        break_minutes=0,
        status=Shift.Status.CONFIRMED,
    )
    TimeEntry.objects.create(
        worker=worker,
        shift=shift,
        clock_in=start,
        clock_out=start + timedelta(hours=8),
        break_minutes=0,
        approved=False,
        wiw_time_id='historical-1',
    )

    sync_working_time(day, day + timedelta(days=1))
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=day)

    assert record.ist_hours == Decimal('8.00')
    assert record.raw_entries[0]['source'] == 'wiw_historical'
    assert record.raw_entries[0]['client_name'] == company.name
    assert record.raw_entries[0]['night_minutes'] > 0


@pytest.mark.django_db
def test_one_time_lexware_bank_import_links_transfer_to_employee_month(
    auth_admin, worker_user
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    period = timezone.localdate().replace(day=1)
    csv_body = (
        'Buchungsdatum;Empfänger;Verwendungszweck;Betrag\n'
        f'05.{period:%m.%Y};Anna Becker;Gehalt {period:%m/%Y};-500,00\n'
    ).encode('utf-8')
    upload = SimpleUploadedFile('lexware.csv', csv_body, content_type='text/csv')

    response = auth_admin.post(
        '/api/working-time/lexware-import/',
        {'period': period.strftime('%Y-%m'), 'file': upload},
        format='multipart',
    )
    assert response.status_code == 200
    assert response.data['employees'][0]['employee_name'] == 'Anna Becker'
    assert response.data['employees'][0]['transferred_amount'] == '500.00'

    statement = PayrollStatement.objects.get(
        worker=worker_user.worker_profile,
        period=period,
    )
    assert statement.transferred_amount == Decimal('500.00')
    assert statement.source == 'lexware_bank_export'
    assert statement.payment_date == period.replace(day=5)
    assert len(statement.raw_data) == 1
