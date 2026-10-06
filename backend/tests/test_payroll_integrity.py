from datetime import date, datetime, time, timedelta
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
def test_rebuild_all_creates_month_for_closed_pending_attendance(
    auth_admin, worker_user, company, location, position
):
    worker = worker_user.worker_profile
    worker.monthly_hours = Decimal('8.00')
    worker.save(update_fields=['monthly_hours', 'updated_at'])

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
    TimeEntry.objects.create(
        worker=worker,
        shift=shift,
        clock_in=start,
        clock_out=start + timedelta(hours=4),
        approved=False,
    )

    response = auth_admin.post('/api/working-time/rebuild-all/', {}, format='json')
    assert response.status_code == 200
    assert response.data['records_count'] >= 1

    record = WorkingTimeAccountRecord.objects.get(
        worker=worker,
        year_month=today.replace(day=1),
    )
    assert record.ist_hours == Decimal('0.00')
    assert record.raw_entries == []

    records_response = auth_admin.get('/api/working-time/records/')
    assert records_response.status_code == 200
    assert records_response.data['count'] >= 1
    assert any(item['id'] == str(record.id) for item in records_response.data['results'])


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
    assert record.employment_type_snapshot == 'minijob'
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
def test_payroll_repairs_implausible_one_day_clockout_rollover(
    worker_user, company, location, position
):
    worker = worker_user.worker_profile
    day = date(2026, 9, 16)
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time(16, 0)), tz)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        break_minutes=30,
        status=Shift.Status.CONFIRMED,
    )
    entry = TimeEntry.objects.create(
        worker=worker,
        shift=shift,
        clock_in=start,
        clock_out=start + timedelta(days=1, hours=6, minutes=30),
        break_minutes=30,
        approved=True,
    )

    sync_working_time(day, day)
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=day.replace(day=1))

    assert record.ist_hours == Decimal('6.00')
    assert len(record.raw_entries) == 1
    audit_row = record.raw_entries[0]
    assert audit_row['worked_minutes'] == 360
    assert audit_row['night_minutes'] == 0
    assert audit_row['clock_out_rollover_corrected'] is True
    source_clock_out = datetime.fromisoformat(audit_row['source_clock_out'])
    assert source_clock_out == entry.clock_out
    corrected_clock_out = datetime.fromisoformat(audit_row['local_clock_out'])
    assert corrected_clock_out.astimezone(tz).date() == day
    assert corrected_clock_out.astimezone(tz).time().replace(tzinfo=None) == time(22, 30)


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
        '"EXTF";700;21;"Buchungsstapel";13;;;;;;;1001;456;;;;;;;1;;0;"EUR"\n'
        'Umsatz (ohne Soll/Haben-Kz);Soll/Haben-Kennzeichen;Belegdatum;Buchungstext\n'
        f'500,00;S;05{period:%m};Gehalt Anna Becker {period:%m/%Y}\n'
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



@pytest.mark.django_db
def test_each_employee_history_starts_with_first_authoritative_work_month(
    worker_user, second_worker, company, location, position
):
    tz = timezone.get_current_timezone()
    cases = [
        (worker_user.worker_profile, date(2026, 1, 5)),
        (second_worker, date(2026, 3, 5)),
    ]
    for worker, work_day in cases:
        start = timezone.make_aware(datetime.combine(work_day, time(8, 0)), tz)
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
            approved=True,
        )

    sync_working_time(date(2026, 1, 1), date(2026, 3, 31))

    first_worker_months = list(
        WorkingTimeAccountRecord.objects
        .filter(worker=worker_user.worker_profile)
        .order_by('year_month')
        .values_list('year_month', flat=True)
    )
    second_worker_months = list(
        WorkingTimeAccountRecord.objects
        .filter(worker=second_worker)
        .order_by('year_month')
        .values_list('year_month', flat=True)
    )

    assert first_worker_months[0] == date(2026, 1, 1)
    assert second_worker_months == [date(2026, 3, 1)]



@pytest.mark.django_db
def test_closed_month_keeps_historical_contract_and_rate_snapshot(
    worker_user, company, location, position
):
    worker = worker_user.worker_profile
    worker.monthly_hours = Decimal('38.00')
    worker.tariff_hourly_rate = Decimal('15.00')
    worker.employment_type = 'minijob'
    worker.save(update_fields=[
        'monthly_hours', 'tariff_hourly_rate', 'employment_type', 'updated_at'
    ])

    month = date(2026, 1, 1)
    start = timezone.make_aware(
        datetime.combine(month + timedelta(days=4), time(8, 0)),
        timezone.get_current_timezone(),
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
        approved=True,
    )

    sync_working_time(month, date(2026, 1, 31))
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=month)
    assert record.soll_hours == Decimal('38.00')
    assert record.hourly_rate == Decimal('15.00')
    assert record.employment_type_snapshot == 'minijob'

    worker.monthly_hours = Decimal('80.00')
    worker.tariff_hourly_rate = Decimal('20.00')
    worker.employment_type = 'teilzeit'
    worker.save(update_fields=[
        'monthly_hours', 'tariff_hourly_rate', 'employment_type', 'updated_at'
    ])
    setting = WorkingTimeSetting.objects.get(worker=worker)
    setting.monthly_limit = Decimal('80.00')
    setting.hourly_rate = Decimal('20.00')
    setting.save(update_fields=['monthly_limit', 'hourly_rate', 'updated_at'])

    sync_working_time(month, date(2026, 1, 31))
    record.refresh_from_db()
    assert record.soll_hours == Decimal('38.00')
    assert record.hourly_rate == Decimal('15.00')
    assert record.employment_type_snapshot == 'minijob'


@pytest.mark.django_db
def test_lexware_import_matches_inactive_former_employee(auth_admin, worker_user):
    from django.core.files.uploadedfile import SimpleUploadedFile

    worker = worker_user.worker_profile
    worker.active = False
    worker.save(update_fields=['active', 'updated_at'])
    period = date(2026, 4, 1)
    upload = SimpleUploadedFile(
        'bank.csv',
        b'Betrag;Datum;Verwendungszweck\n500,00;15.04.2026;Gehalt Anna Becker\n',
        content_type='text/csv',
    )
    response = auth_admin.post(
        '/api/working-time/lexware-import/',
        {'period': '2026-04', 'file': upload},
        format='multipart',
    )
    assert response.status_code == 200
    assert response.data['employees'][0]['worker_id'] == str(worker.id)
    assert PayrollStatement.objects.get(worker=worker, period=period).transferred_amount == Decimal('500.00')


@pytest.mark.django_db
def test_lexware_import_rejects_ambiguous_employee_name(auth_admin, worker_user, second_worker):
    from django.core.files.uploadedfile import SimpleUploadedFile

    second_worker.user.first_name = 'Anna'
    second_worker.user.last_name = 'Becker'
    second_worker.user.save(update_fields=['first_name', 'last_name'])
    upload = SimpleUploadedFile(
        'bank.csv',
        b'Betrag;Datum;Verwendungszweck\n500,00;15.04.2026;Gehalt Anna Becker\n',
        content_type='text/csv',
    )
    response = auth_admin.post(
        '/api/working-time/lexware-import/',
        {'period': '2026-04', 'file': upload},
        format='multipart',
    )
    assert response.status_code == 200
    assert response.data['employees'] == []
    assert response.data['unmatched_count'] == 1
    assert not PayrollStatement.objects.filter(period=date(2026, 4, 1)).exists()
