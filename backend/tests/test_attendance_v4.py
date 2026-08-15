from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from core.absence_models import ShiftAbsenceCase
from core.attendance_v4_models import (
    AttendanceAttestation,
    AttendanceBreak,
    AttendanceNotice,
    AttendancePolicy,
    AttendanceTerminal,
)
from core.attendance_v4_service import (
    clock_in_worker,
    clock_out_worker,
    end_break,
    net_worked_minutes,
    scan_attendance_notices,
    start_break,
    submit_attestation,
)
from core.models import Shift, TimeEntry
from core.shift_slots import ShiftSlot


pytestmark = pytest.mark.django_db


def policy_for(location, **overrides):
    defaults = {
        'name': 'Test Policy',
        'location': location,
        'priority': 100,
        'early_clock_in_mode': AttendancePolicy.Enforcement.OFF,
        'clock_in_location_mode': AttendancePolicy.Enforcement.OFF,
        'clock_out_location_mode': AttendancePolicy.Enforcement.OFF,
        'required_break_after_minutes': 360,
        'required_break_minutes': 30,
    }
    defaults.update(overrides)
    return AttendancePolicy.objects.create(**defaults)


def claim_fixture_slot(shift, worker):
    slot = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).first()
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'attendance_v4_test'
    slot.claimed_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    return slot


def test_early_clock_in_can_be_blocked(worker_user, shift, location):
    policy_for(location, early_clock_in_mode=AttendancePolicy.Enforcement.BLOCK, early_clock_in_minutes=15)
    too_early = shift.starts_at - timedelta(minutes=45)
    with pytest.raises(ValidationError):
        clock_in_worker(worker=worker_user.worker_profile, shift_id=shift.id, now=too_early)
    assert not TimeEntry.objects.filter(worker=worker_user.worker_profile).exists()
    assert not AttendanceNotice.objects.filter(notice_type=AttendanceNotice.Type.EARLY_CLOCK_IN).exists()


def test_late_clock_in_creates_notice(worker_user, shift, location):
    policy_for(location, late_clock_in_grace_minutes=5)
    entry = clock_in_worker(worker=worker_user.worker_profile, shift_id=shift.id, now=shift.starts_at + timedelta(minutes=12))
    assert entry.clock_in == shift.starts_at + timedelta(minutes=12)
    notice = AttendanceNotice.objects.get(notice_type=AttendanceNotice.Type.LATE_CLOCK_IN, entry__isnull=True)
    assert notice.value_minutes == 12


def test_actual_unpaid_break_reduces_net_time(worker_user, shift, location):
    policy_for(location, required_break_after_minutes=120, required_break_minutes=30, default_break_paid=False)
    entry = clock_in_worker(worker=worker_user.worker_profile, shift_id=shift.id, now=shift.starts_at)
    record = start_break(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=2))
    record = end_break(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=2, minutes=30))
    assert record.status == AttendanceBreak.Status.COMPLETED
    assert record.actual_minutes == 30
    entry, _ = clock_out_worker(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=4))
    assert net_worked_minutes(entry) == 210


def test_paid_break_is_not_deducted(worker_user, shift, location):
    policy_for(location, required_break_after_minutes=120, required_break_minutes=20, default_break_paid=True)
    entry = clock_in_worker(worker=worker_user.worker_profile, shift_id=shift.id, now=shift.starts_at)
    record = start_break(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=1))
    assert record.paid is True
    end_break(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=1, minutes=20))
    entry, _ = clock_out_worker(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=4))
    assert net_worked_minutes(entry) == 240


def test_auto_deduct_adds_only_missing_unpaid_break(worker_user, shift, location):
    policy_for(
        location,
        required_break_after_minutes=120,
        required_break_minutes=30,
        default_break_paid=False,
        auto_deduct_unpaid_breaks=True,
    )
    entry = clock_in_worker(worker=worker_user.worker_profile, shift_id=shift.id, now=shift.starts_at)
    start_break(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=1))
    end_break(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=1, minutes=10))
    entry, _ = clock_out_worker(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=4))
    auto = AttendanceBreak.objects.get(entry=entry, source=AttendanceBreak.Source.AUTO_DEDUCT)
    assert auto.deducted_minutes == 20
    assert net_worked_minutes(entry) == 210


def test_break_attestation_resolves_missing_notice(worker_user, shift, location):
    policy_for(location, break_attestation_required=True)
    entry = clock_in_worker(worker=worker_user.worker_profile, shift_id=shift.id, now=shift.starts_at)
    entry, _ = clock_out_worker(worker=worker_user.worker_profile, now=shift.starts_at + timedelta(hours=2))
    notice = AttendanceNotice.objects.get(entry=entry, notice_type=AttendanceNotice.Type.ATTESTATION_MISSING)
    obj = submit_attestation(
        entry=entry,
        worker=worker_user.worker_profile,
        kind=AttendanceAttestation.Kind.BREAK,
        answers={'breaks_taken': True},
        note='Bestätigt',
    )
    assert obj.answers['breaks_taken'] is True
    notice.refresh_from_db()
    assert notice.status == AttendanceNotice.Status.RESOLVED


def test_no_show_scan_creates_notice_and_coverage_case(worker_user, shift, location):
    policy_for(location, no_show_after_minutes=15, late_clock_in_grace_minutes=5)
    slot = claim_fixture_slot(shift, worker_user.worker_profile)
    shift.starts_at = timezone.now() - timedelta(minutes=40)
    shift.ends_at = timezone.now() + timedelta(hours=4)
    shift.status = Shift.Status.CONFIRMED
    shift.save(update_fields=['starts_at', 'ends_at', 'status', 'updated_at'])
    result = scan_attendance_notices()
    assert result['no_show'] == 1
    assert AttendanceNotice.objects.filter(worker=worker_user.worker_profile, shift=shift, notice_type=AttendanceNotice.Type.NO_SHOW).exists()
    case = ShiftAbsenceCase.objects.get(slot=slot)
    assert case.source == ShiftAbsenceCase.Source.ATTENDANCE
    assert case.kind == ShiftAbsenceCase.Kind.NO_SHOW


def test_missed_clock_out_scan_creates_notice(worker_user, shift, location):
    policy_for(location, missed_clock_out_after_minutes=30)
    slot = claim_fixture_slot(shift, worker_user.worker_profile)
    shift.starts_at = timezone.now() - timedelta(hours=3)
    shift.ends_at = timezone.now() - timedelta(hours=1)
    shift.status = Shift.Status.CONFIRMED
    shift.save(update_fields=['starts_at', 'ends_at', 'status', 'updated_at'])
    entry = TimeEntry.objects.create(worker=worker_user.worker_profile, shift=shift, clock_in=shift.starts_at)
    result = scan_attendance_notices()
    assert result['missed_clock_out'] == 1
    assert AttendanceNotice.objects.filter(entry=entry, notice_type=AttendanceNotice.Type.MISSED_CLOCK_OUT).exists()


def test_terminal_requires_photo_and_accepts_authenticated_clock_in(worker_user, shift, location):
    policy_for(location, terminal_photo_clock_in=True)
    token = AttendanceTerminal.issue_token()
    terminal = AttendanceTerminal.objects.create(
        name='Empfang',
        location=location,
        token_hash=AttendanceTerminal.hash_token(token),
        photo_clock_in=True,
    )
    client = APIClient()
    url = f'/api/attendance/terminal/{terminal.public_id}/clock/'
    missing = client.post(url, {'identity': worker_user.worker_profile.employee_number, 'action': 'clock_in', 'shift': str(shift.id), 'terminal_token': token}, format='multipart')
    assert missing.status_code == 400
    photo = SimpleUploadedFile('clock.jpg', b'fake-jpeg-bytes', content_type='image/jpeg')
    response = client.post(
        url,
        {'identity': worker_user.worker_profile.employee_number, 'action': 'clock_in', 'shift': str(shift.id), 'terminal_token': token, 'photo': photo},
        format='multipart',
    )
    assert response.status_code == 201
    assert response.data['action'] == 'clock_in'
    terminal.refresh_from_db()
    assert terminal.last_seen_at is not None


def test_worker_break_api_roundtrip(auth_worker, worker_user, shift, location):
    policy_for(location, required_break_after_minutes=120, required_break_minutes=15)
    TimeEntry.objects.create(worker=worker_user.worker_profile, shift=shift, clock_in=timezone.now())
    started = auth_worker.post('/api/attendance/breaks/start/', {}, format='json')
    assert started.status_code == 201
    ended = auth_worker.post('/api/attendance/breaks/end/', {}, format='json')
    assert ended.status_code == 200
    assert ended.data['status'] == AttendanceBreak.Status.COMPLETED


def test_manager_can_resolve_attendance_notice(auth_admin, worker_user, shift):
    notice = AttendanceNotice.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        notice_type=AttendanceNotice.Type.LATE_CLOCK_IN,
        dedupe_key='manager-resolve-test',
    )
    response = auth_admin.post(f'/api/attendance-notices/{notice.id}/resolve/', {'note': 'geprüft'}, format='json')
    assert response.status_code == 200
    notice.refresh_from_db()
    assert notice.status == AttendanceNotice.Status.RESOLVED
    assert notice.resolved_by_id is not None
