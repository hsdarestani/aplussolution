from datetime import timedelta

import pytest
from django.utils import timezone

from core.absence_models import ShiftAbsenceCase
from core.attendance_final_service import scan_attendance_notices_final
from core.attendance_v4_models import AttendanceClockEvent, AttendanceNotice, AttendancePolicy, AttendanceTerminal
from core.models import TimeEntry
from core.reporting_service import build_report, field_catalog
from core.shift_slots import ShiftSlot


pytestmark = pytest.mark.django_db


def final_policy(location, **overrides):
    defaults = {
        'name': 'Final parity',
        'location': location,
        'priority': 500,
        'early_clock_in_mode': AttendancePolicy.Enforcement.OFF,
        'clock_in_location_mode': AttendancePolicy.Enforcement.OFF,
        'clock_out_location_mode': AttendancePolicy.Enforcement.OFF,
        'computer_ip_mode': AttendancePolicy.Enforcement.OFF,
    }
    defaults.update(overrides)
    return AttendancePolicy.objects.create(**defaults)


def claimed_slot(shift, worker):
    slot = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).first()
    assert slot is not None
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'final-parity-test'
    slot.claimed_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    return slot


def test_web_clock_is_blocked_outside_ip_allowlist(auth_worker, worker_user, shift, location):
    final_policy(
        location,
        computer_ip_mode=AttendancePolicy.Enforcement.BLOCK,
        allowed_ip_networks=['203.0.113.10/32'],
    )
    response = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id)},
        format='json',
        REMOTE_ADDR='198.51.100.7',
    )
    assert response.status_code == 400
    assert 'IP-Adresse' in response.data['detail']
    assert not TimeEntry.objects.filter(worker=worker_user.worker_profile).exists()
    notice = AttendanceNotice.objects.get(worker=worker_user.worker_profile, notice_type=AttendanceNotice.Type.WRONG_LOCATION)
    assert notice.details['restriction'] == 'ip'
    assert notice.details['ip_address'] == '198.51.100.7'


def test_web_clock_records_allowed_ip_and_web_method(auth_worker, worker_user, shift, location):
    final_policy(
        location,
        computer_ip_mode=AttendancePolicy.Enforcement.BLOCK,
        allowed_ip_networks=['203.0.113.0/24'],
    )
    response = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id)},
        format='json',
        REMOTE_ADDR='203.0.113.42',
    )
    assert response.status_code == 201
    event = AttendanceClockEvent.objects.get(entry_id=response.data['id'], kind=AttendanceClockEvent.Kind.CLOCK_IN)
    assert event.ip_address == '203.0.113.42'
    assert event.method == AttendanceClockEvent.Method.WEB


def test_mobile_clock_uses_geofence_path_not_computer_ip(auth_worker, worker_user, shift, location):
    final_policy(
        location,
        computer_ip_mode=AttendancePolicy.Enforcement.BLOCK,
        allowed_ip_networks=['203.0.113.10/32'],
    )
    response = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id), 'clock_client': 'mobile'},
        format='json',
        REMOTE_ADDR='198.51.100.7',
    )
    assert response.status_code == 201
    event = AttendanceClockEvent.objects.get(entry_id=response.data['id'], kind=AttendanceClockEvent.Kind.CLOCK_IN)
    assert event.method == AttendanceClockEvent.Method.MOBILE


def test_missed_clock_in_becomes_no_show_only_after_shift_end(worker_user, shift, location):
    final_policy(location, late_clock_in_grace_minutes=5)
    slot = claimed_slot(shift, worker_user.worker_profile)
    now = timezone.now()
    shift.starts_at = now - timedelta(minutes=40)
    shift.ends_at = now + timedelta(hours=1)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])

    during = scan_attendance_notices_final(now=now)
    assert during['missed_clock_in'] == 1
    assert during['no_show'] == 0
    missed = AttendanceNotice.objects.get(worker=worker_user.worker_profile, shift=shift, notice_type=AttendanceNotice.Type.MISSED_CLOCK_IN)
    assert missed.status == AttendanceNotice.Status.OPEN
    assert not ShiftAbsenceCase.objects.filter(slot=slot).exists()

    after = now + timedelta(hours=1, minutes=1)
    finished = scan_attendance_notices_final(now=after)
    assert finished['no_show'] == 1
    missed.refresh_from_db()
    assert missed.status == AttendanceNotice.Status.RESOLVED
    no_show = AttendanceNotice.objects.get(worker=worker_user.worker_profile, shift=shift, notice_type=AttendanceNotice.Type.NO_SHOW)
    assert no_show.status == AttendanceNotice.Status.OPEN
    case = ShiftAbsenceCase.objects.get(slot=slot)
    assert case.kind == ShiftAbsenceCase.Kind.NO_SHOW


def test_all_schedules_terminal_can_clock_assigned_shift_without_personal_restrictions(api_client, worker_user, shift, location):
    final_policy(
        location,
        clock_in_location_mode=AttendancePolicy.Enforcement.BLOCK,
        computer_ip_mode=AttendancePolicy.Enforcement.BLOCK,
        allowed_ip_networks=['203.0.113.10/32'],
    )
    token = AttendanceTerminal.issue_token()
    terminal = AttendanceTerminal.objects.create(
        name='Zentrale Kasse',
        scope_mode=AttendanceTerminal.ScopeMode.ALL,
        location=None,
        token_hash=AttendanceTerminal.hash_token(token),
    )
    response = api_client.post(
        f'/api/attendance/terminal/{terminal.public_id}/clock/',
        {
            'identity': worker_user.worker_profile.employee_number,
            'action': 'clock_in',
            'shift': str(shift.id),
            'terminal_token': token,
        },
        format='multipart',
        REMOTE_ADDR='198.51.100.7',
    )
    assert response.status_code == 201
    assert response.data['terminal_scope'] == AttendanceTerminal.ScopeMode.ALL
    event = AttendanceClockEvent.objects.get(entry__worker=worker_user.worker_profile, kind=AttendanceClockEvent.Kind.CLOCK_IN)
    assert event.method == AttendanceClockEvent.Method.TERMINAL


def test_attendance_exceptions_are_rolling_seven_days_and_can_be_cleared(auth_admin, worker_user, shift):
    old = AttendanceNotice.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        notice_type=AttendanceNotice.Type.LATE_CLOCK_IN,
        detected_at=timezone.now() - timedelta(days=8),
        dedupe_key='old-eight-day-notice',
    )
    recent = AttendanceNotice.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        notice_type=AttendanceNotice.Type.MISSED_CLOCK_IN,
        detected_at=timezone.now() - timedelta(days=2),
        dedupe_key='recent-two-day-notice',
    )
    response = auth_admin.get('/api/attendance/exceptions/')
    assert response.status_code == 200
    assert response.data['notice_window_days'] == 7
    ids = {row['id'] for row in response.data['notices']}
    assert str(recent.id) in ids
    assert str(old.id) not in ids

    cleared = auth_admin.post('/api/attendance-notices/clear-recent/', {}, format='json')
    assert cleared.status_code == 200
    assert cleared.data['cleared'] == 1
    recent.refresh_from_db()
    old.refresh_from_db()
    assert recent.status == AttendanceNotice.Status.DISMISSED
    assert old.status == AttendanceNotice.Status.OPEN


def test_times_report_exposes_clock_ip_method_and_coordinates(admin_user, worker_user, shift):
    entry = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=timezone.now() - timedelta(hours=1),
        clock_out=timezone.now(),
        clock_in_lat='50.110000',
        clock_in_lng='8.680000',
        clock_out_lat='50.110100',
        clock_out_lng='8.680100',
    )
    AttendanceClockEvent.objects.create(
        entry=entry,
        kind=AttendanceClockEvent.Kind.CLOCK_IN,
        method=AttendanceClockEvent.Method.WEB,
        occurred_at=entry.clock_in,
        ip_address='203.0.113.42',
        lat='50.110000',
        lng='8.680000',
    )
    AttendanceClockEvent.objects.create(
        entry=entry,
        kind=AttendanceClockEvent.Kind.CLOCK_OUT,
        method=AttendanceClockEvent.Method.WEB,
        occurred_at=entry.clock_out,
        ip_address='203.0.113.43',
        lat='50.110100',
        lng='8.680100',
    )
    available = {item['key'] for item in field_catalog(admin_user, 'times')}
    assert {'clock_in_ip', 'clock_out_ip', 'clock_in_method', 'clock_out_method'} <= available
    result = build_report(
        admin_user,
        'times',
        columns=['employee_name', 'clock_in_ip', 'clock_out_ip', 'clock_in_method', 'clock_out_method', 'clock_in_lat'],
        filters={'date_from': timezone.localdate().isoformat(), 'date_to': timezone.localdate().isoformat()},
    )
    row = next(item for item in result['rows'] if item['employee_name'] == 'Anna Becker')
    assert row['clock_in_ip'] == '203.0.113.42'
    assert row['clock_out_ip'] == '203.0.113.43'
    assert row['clock_in_method'] == AttendanceClockEvent.Method.WEB
    assert str(row['clock_in_lat']) == '50.110000'
