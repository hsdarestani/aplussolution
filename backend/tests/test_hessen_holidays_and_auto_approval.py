from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.hessen_holidays import (
    hessen_public_holidays,
    hessen_holiday,
    holiday_tax_exempt_ceiling_percent,
)
from core.models import Shift, TimeEntry, WorkingTimeAccountRecord, WorkingTimeSetting
from core.payroll_engine import _entry_metrics, sync_working_time
from core.working_time import record_dict


def local_datetime(year, month, day, hour, minute=0):
    return timezone.make_aware(
        datetime(year, month, day, hour, minute), timezone.get_current_timezone()
    )


def test_hessen_calendar_2026_matches_official_ten_days():
    assert hessen_public_holidays(2026) == {
        date(2026, 1, 1): 'Neujahr',
        date(2026, 4, 3): 'Karfreitag',
        date(2026, 4, 6): 'Ostermontag',
        date(2026, 5, 1): 'Tag der Arbeit',
        date(2026, 5, 14): 'Christi Himmelfahrt',
        date(2026, 5, 25): 'Pfingstmontag',
        date(2026, 6, 4): 'Fronleichnam',
        date(2026, 10, 3): 'Tag der Deutschen Einheit',
        date(2026, 12, 25): '1. Weihnachtsfeiertag',
        date(2026, 12, 26): '2. Weihnachtsfeiertag',
    }
    assert hessen_holiday(date(2026, 4, 4)) is None
    assert holiday_tax_exempt_ceiling_percent(date(2026, 4, 3)) == 125
    assert holiday_tax_exempt_ceiling_percent(date(2026, 5, 1)) == 150


def test_attendance_pdf_uses_same_holiday_split():
    from core.schedule_reports import _attendance_metrics

    start = local_datetime(2026, 4, 2, 23)
    end = local_datetime(2026, 4, 3, 4)
    entry = TimeEntry(
        clock_in=start,
        clock_out=end,
        break_minutes=60,
    )
    metrics = _attendance_metrics(entry, start, end)
    assert metrics['holiday'] == 192
    assert metrics['net'] == 240


def test_cross_midnight_holiday_minutes_are_prorated_for_break():
    entry = TimeEntry(
        clock_in=local_datetime(2026, 4, 2, 23),
        clock_out=local_datetime(2026, 4, 3, 4),
        break_minutes=60,
    )
    metrics = _entry_metrics(entry, timezone.get_current_timezone())
    assert metrics['worked_minutes'] == 240
    assert metrics['holiday_minutes'] == 192
    assert metrics['holiday_details'] == [{
        'date': '2026-04-03',
        'name': 'Karfreitag',
        'minutes': 192,
        'tax_exempt_ceiling_percent': 125,
    }]


@pytest.mark.django_db
def test_worker_reports_completed_shift_without_manual_approval(
    auth_worker, worker_user, shift
):
    shift.starts_at = timezone.now() - timedelta(hours=5)
    shift.ends_at = timezone.now() - timedelta(hours=1)
    shift.status = Shift.Status.CONFIRMED
    shift.save(update_fields=['starts_at', 'ends_at', 'status', 'updated_at'])
    response = auth_worker.post(
        '/api/time-entries/report_shift/',
        {
            'shift': str(shift.id),
            'clock_in': (shift.starts_at + timedelta(minutes=5)).isoformat(),
            'clock_out': (shift.ends_at - timedelta(minutes=5)).isoformat(),
            'legal_acknowledged': True,
        },
        format='json',
    )
    assert response.status_code == 201, response.data
    assert response.data['review_required'] is False
    entry = TimeEntry.objects.get(worker=worker_user.worker_profile, shift=shift)
    assert entry.approved is True
    assert entry.approved_by_id is None


@pytest.mark.django_db
def test_holiday_hours_and_configured_payment_flow_into_monthly_record(
    worker_user, company, location, position
):
    worker = worker_user.worker_profile
    worker.monthly_hours = Decimal('10')
    worker.tariff_hourly_rate = Decimal('20')
    worker.save(update_fields=['monthly_hours', 'tariff_hourly_rate', 'updated_at'])
    WorkingTimeSetting.objects.create(
        worker=worker, monthly_limit=Decimal('10'), hourly_rate=Decimal('20'),
        holiday_surcharge_percent=Decimal('25'),
    )
    start = local_datetime(2026, 5, 1, 9)
    shift = Shift.objects.create(
        client=company, location=location, position=position,
        worker=worker, starts_at=start, ends_at=start + timedelta(hours=4),
        status=Shift.Status.CONFIRMED,
    )
    TimeEntry.objects.create(
        worker=worker, shift=shift, clock_in=start,
        clock_out=start + timedelta(hours=4), approved=True, break_minutes=0,
    )
    sync_working_time(date(2026, 5, 1), date(2026, 5, 31))
    record = WorkingTimeAccountRecord.objects.get(worker=worker, year_month=date(2026, 5, 1))
    row = record_dict(record)
    assert row['holiday_hours'] == '4.00'
    assert row['holiday_surcharge_amount'] == '20.00'
    assert row['surcharge_amount'] == '20.00'
    assert record.raw_entries[0]['holiday_details'][0]['name'] == 'Tag der Arbeit'
