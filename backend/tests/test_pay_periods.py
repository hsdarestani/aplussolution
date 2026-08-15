from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from core.attendance_models import TimeEntryCorrection
from core.attendance_v4_models import AttendanceBreak
from core.models import TimeEntry
from core.payroll_models import PayPeriod, TimesheetEntry, TimesheetException, WorkerTimesheet
from core.payroll_service import (
    approve_timesheet,
    assert_time_entry_editable,
    close_period,
    reopen_period,
    sync_period,
)
from core.shift_slots import ShiftSlot


pytestmark = pytest.mark.django_db


def period_for(entry, admin_user):
    day = timezone.localdate(entry.clock_in)
    return PayPeriod.objects.create(name='Testperiode', starts_on=day, ends_on=day, created_by=admin_user)


def completed_entry(worker_user, shift, hours=8, approved=False, approved_by=None):
    end = timezone.now() - timedelta(minutes=5)
    start = end - timedelta(hours=hours)
    shift.starts_at = start
    shift.ends_at = end
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    return TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=start,
        clock_out=end,
        approved=approved,
        approved_by=approved_by,
    )


def test_sync_uses_actual_breaks_for_net_and_estimated_pay(worker_user, shift, admin_user):
    entry = completed_entry(worker_user, shift, approved=False)
    AttendanceBreak.objects.create(
        entry=entry,
        status=AttendanceBreak.Status.COMPLETED,
        source=AttendanceBreak.Source.MANUAL,
        paid=False,
        started_at=entry.clock_in + timedelta(hours=3),
        ended_at=entry.clock_in + timedelta(hours=3, minutes=30),
    )
    AttendanceBreak.objects.create(
        entry=entry,
        status=AttendanceBreak.Status.COMPLETED,
        source=AttendanceBreak.Source.MANUAL,
        paid=True,
        started_at=entry.clock_in + timedelta(hours=5),
        ended_at=entry.clock_in + timedelta(hours=5, minutes=15),
    )
    period = period_for(entry, admin_user)
    sync_period(period)

    sheet = WorkerTimesheet.objects.get(pay_period=period, worker=worker_user.worker_profile)
    snapshot = sheet.entries.get()
    assert snapshot.gross_minutes == 480
    assert snapshot.paid_break_minutes == 15
    assert snapshot.unpaid_break_minutes == 30
    assert snapshot.net_minutes == 450
    assert snapshot.hourly_rate == Decimal('14.50')
    assert snapshot.amount_estimate == Decimal('108.75')
    assert sheet.net_minutes == 450
    assert TimesheetException.objects.filter(timesheet=sheet, exception_type=TimesheetException.Type.UNAPPROVED_ENTRY, status='open').exists()


def test_pending_correction_is_blocking_payroll_exception(worker_user, shift, admin_user):
    entry = completed_entry(worker_user, shift, approved=True, approved_by=admin_user)
    period = period_for(entry, admin_user)
    TimeEntryCorrection.objects.create(
        entry=entry,
        requested_by=worker_user.worker_profile,
        requested_clock_out=entry.clock_out + timedelta(minutes=15),
        reason='Arbeitsende war später als erfasst.',
    )
    sync_period(period)
    sheet = WorkerTimesheet.objects.get(pay_period=period, worker=worker_user.worker_profile)
    assert sheet.blocking_exception_count == 1
    assert sheet.exceptions.filter(exception_type=TimesheetException.Type.PENDING_CORRECTION, status='open').exists()
    with pytest.raises(ValidationError):
        approve_timesheet(sheet, admin_user)


def test_close_locks_time_entry_and_reopen_unlocks(worker_user, shift, admin_user):
    entry = completed_entry(worker_user, shift, approved=True, approved_by=admin_user)
    period = period_for(entry, admin_user)
    sync_period(period)
    sheet = WorkerTimesheet.objects.get(pay_period=period, worker=worker_user.worker_profile)
    approve_timesheet(sheet, admin_user)
    close_period(period, admin_user)

    period.refresh_from_db()
    sheet.refresh_from_db()
    assert period.status == PayPeriod.Status.CLOSED
    assert sheet.status == WorkerTimesheet.Status.LOCKED
    assert TimesheetEntry.objects.get(time_entry=entry).locked is True
    with pytest.raises(ValidationError):
        assert_time_entry_editable(entry)

    reopen_period(period, admin_user, 'Korrektur erforderlich')
    period.refresh_from_db()
    assert period.status == PayPeriod.Status.OPEN
    assert_time_entry_editable(entry)


def test_missing_completed_shift_creates_blocker(worker_user, shift, admin_user):
    now = timezone.now()
    shift.starts_at = now - timedelta(hours=6)
    shift.ends_at = now - timedelta(hours=1)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    slot = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).first()
    slot.worker = worker_user.worker_profile
    slot.status = ShiftSlot.Status.CLAIMED
    slot.claimed_at = now - timedelta(hours=7)
    slot.save(update_fields=['worker', 'status', 'claimed_at', 'updated_at'])
    period = PayPeriod.objects.create(name='Missing', starts_on=timezone.localdate(shift.starts_at), ends_on=timezone.localdate(shift.starts_at), created_by=admin_user)
    sync_period(period)
    sheet = WorkerTimesheet.objects.get(pay_period=period, worker=worker_user.worker_profile)
    assert sheet.blocking_exception_count == 1
    assert sheet.exceptions.filter(exception_type=TimesheetException.Type.MISSING_ENTRY, status='open').exists()


def test_pay_period_api_sync_approve_close_and_exports(auth_admin, worker_user, shift, admin_user):
    entry = completed_entry(worker_user, shift, approved=True, approved_by=admin_user)
    day = timezone.localdate(entry.clock_in)
    created = auth_admin.post('/api/pay-periods/', {'name': 'August Test', 'starts_on': day.isoformat(), 'ends_on': day.isoformat(), 'currency': 'EUR'}, format='json')
    assert created.status_code == 201
    period_id = created.data['id']
    synced = auth_admin.post(f'/api/pay-periods/{period_id}/sync/', {}, format='json')
    assert synced.status_code == 200
    sheet = WorkerTimesheet.objects.get(pay_period_id=period_id)
    approved = auth_admin.post(f'/api/timesheets/{sheet.id}/approve/', {}, format='json')
    assert approved.status_code == 200
    closed = auth_admin.post(f'/api/pay-periods/{period_id}/close/', {}, format='json')
    assert closed.status_code == 200
    csv_response = auth_admin.get(f'/api/pay-periods/{period_id}/export-csv/')
    xlsx_response = auth_admin.get(f'/api/pay-periods/{period_id}/export-xlsx/')
    assert csv_response.status_code == 200
    assert 'Personalnummer' in csv_response.content.decode('utf-8-sig')
    assert xlsx_response.status_code == 200
    assert xlsx_response['Content-Type'].startswith('application/vnd.openxmlformats')


def test_overlapping_pay_period_is_rejected(auth_admin):
    first = auth_admin.post('/api/pay-periods/', {'name': 'P1', 'starts_on': '2026-08-01', 'ends_on': '2026-08-15'}, format='json')
    assert first.status_code == 201
    second = auth_admin.post('/api/pay-periods/', {'name': 'P2', 'starts_on': '2026-08-10', 'ends_on': '2026-08-31'}, format='json')
    assert second.status_code == 400
