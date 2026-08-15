from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.absence_models import ShiftAbsenceCase
from core.attendance_models import TimeEntryCorrection
from core.attendance_v4_models import AttendanceNotice
from core.models import ClientCompany, Location, Shift, TimeEntry
from core.workplace_access import seed_system_roles
from core.workplace_models import AccessRole, UserAccessAssignment


pytestmark = pytest.mark.django_db


def scoped_manager(manager_user, location, worker):
    seed_system_roles()
    role = AccessRole.objects.get(code='supervisor')
    assignment = UserAccessAssignment.objects.create(
        user=manager_user,
        access_role=role,
        scope_mode=UserAccessAssignment.ScopeMode.SCOPED,
    )
    assignment.locations.add(location)
    assignment.workers.add(worker)
    client = APIClient()
    client.force_authenticate(manager_user)
    return client


def foreign_shift(second_worker, position):
    company = ClientCompany.objects.create(name='Foreign GmbH', customer_number='KD-FOREIGN', address='Berlin')
    location = Location.objects.create(client=company, name='Berlin Einsatz', address='Berlin')
    start = timezone.now() + timedelta(days=2)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=second_worker,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        status=Shift.Status.DRAFT,
        required_count=1,
    )
    return location, shift


def unpack(response):
    body = response.json()
    return body if isinstance(body, list) else body.get('results', [])


def test_scoped_manager_cannot_read_or_resolve_foreign_attendance_notice(
    manager_user, worker_user, second_worker, shift, location, position
):
    _, outside_shift = foreign_shift(second_worker, position)
    inside = AttendanceNotice.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        notice_type=AttendanceNotice.Type.LATE_CLOCK_IN,
        dedupe_key='scope-local-notice',
    )
    outside = AttendanceNotice.objects.create(
        worker=second_worker,
        shift=outside_shift,
        notice_type=AttendanceNotice.Type.LATE_CLOCK_IN,
        dedupe_key='scope-foreign-notice',
    )
    client = scoped_manager(manager_user, location, worker_user.worker_profile)

    response = client.get('/api/attendance-notices/')
    assert response.status_code == 200
    ids = {row['id'] for row in unpack(response)}
    assert str(inside.id) in ids
    assert str(outside.id) not in ids

    denied = client.post(f'/api/attendance-notices/{outside.id}/resolve/', {'note': 'should not work'}, format='json')
    assert denied.status_code == 404
    outside.refresh_from_db()
    assert outside.status == AttendanceNotice.Status.OPEN


def test_scoped_manager_cannot_mutate_foreign_timer_or_correction(
    manager_user, worker_user, second_worker, location, position
):
    _, outside_shift = foreign_shift(second_worker, position)
    now = timezone.now() - timedelta(hours=2)
    running = TimeEntry.objects.create(worker=second_worker, shift=outside_shift, clock_in=now)
    closed = TimeEntry.objects.create(
        worker=second_worker,
        shift=outside_shift,
        clock_in=now - timedelta(days=1),
        clock_out=now - timedelta(days=1) + timedelta(hours=4),
    )
    correction = TimeEntryCorrection.objects.create(
        entry=closed,
        requested_by=second_worker,
        requested_clock_out=closed.clock_out + timedelta(minutes=15),
        reason='Korrektur außerhalb Scope',
    )
    client = scoped_manager(manager_user, location, worker_user.worker_profile)

    response = client.post(f'/api/attendance/entries/{running.id}/close/', {'reason': 'Manager correction'}, format='json')
    assert response.status_code == 404
    running.refresh_from_db()
    assert running.clock_out is None

    response = client.post(
        f'/api/attendance/corrections/{correction.id}/decide/',
        {'status': TimeEntryCorrection.Status.APPROVED},
        format='json',
    )
    assert response.status_code == 404
    correction.refresh_from_db()
    assert correction.status == TimeEntryCorrection.Status.PENDING


def test_absence_and_callout_are_scoped_by_shift_location(
    manager_user, worker_user, second_worker, shift, location, position
):
    _, outside_shift = foreign_shift(second_worker, position)
    inside = ShiftAbsenceCase.objects.create(
        shift=shift,
        absent_worker=worker_user.worker_profile,
        kind=ShiftAbsenceCase.Kind.SICK,
        source=ShiftAbsenceCase.Source.MANAGER,
    )
    outside = ShiftAbsenceCase.objects.create(
        shift=outside_shift,
        absent_worker=second_worker,
        kind=ShiftAbsenceCase.Kind.SICK,
        source=ShiftAbsenceCase.Source.MANAGER,
    )
    client = scoped_manager(manager_user, location, worker_user.worker_profile)

    response = client.get('/api/absence-cases/')
    assert response.status_code == 200
    ids = {row['id'] for row in unpack(response)}
    assert str(inside.id) in ids
    assert str(outside.id) not in ids

    response = client.post(
        '/api/operations/callouts/report/',
        {'shift': str(outside_shift.id), 'worker': str(second_worker.id), 'kind': 'sick'},
        format='json',
    )
    assert response.status_code == 403


def test_legacy_payroll_export_cannot_bypass_payroll_export_capability(
    manager_user, worker_user, location
):
    client = scoped_manager(manager_user, location, worker_user.worker_profile)
    response = client.get('/api/reports/payroll-estimate.csv')
    assert response.status_code == 403


def test_operations_search_locations_and_timeoff_stay_inside_scope(
    manager_user, worker_user, second_worker, shift, location, position
):
    outside_location, outside_shift = foreign_shift(second_worker, position)
    client = scoped_manager(manager_user, location, worker_user.worker_profile)

    operations = client.get('/api/operations/')
    assert operations.status_code == 200
    assert operations.json()['active_workers'] == 1

    search = client.get('/api/search/global/?q=Lukas')
    assert search.status_code == 200
    assert search.json()['groups']['workers'] == []

    locations = client.get('/api/locations/')
    assert locations.status_code == 200
    location_ids = {row['id'] for row in unpack(locations)}
    assert str(location.id) in location_ids
    assert str(outside_location.id) not in location_ids

    from core.models import TimeOffRequest
    local_request = TimeOffRequest.objects.create(
        worker=worker_user.worker_profile,
        starts_on=timezone.localdate() + timedelta(days=4),
        ends_on=timezone.localdate() + timedelta(days=5),
        reason='Local',
    )
    outside_request = TimeOffRequest.objects.create(
        worker=second_worker,
        starts_on=timezone.localdate() + timedelta(days=4),
        ends_on=timezone.localdate() + timedelta(days=5),
        reason='Foreign',
    )
    response = client.get('/api/time-off/')
    assert response.status_code == 200
    request_ids = {row['id'] for row in unpack(response)}
    assert str(local_request.id) in request_ids
    assert str(outside_request.id) not in request_ids


def test_bulk_publish_updates_only_scoped_shifts(
    manager_user, worker_user, second_worker, company, shift, location, position
):
    _, outside_shift = foreign_shift(second_worker, position)
    local_start = timezone.now() + timedelta(days=3)
    local_shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=local_start,
        ends_at=local_start + timedelta(hours=5),
        status=Shift.Status.DRAFT,
        required_count=1,
    )
    client = scoped_manager(manager_user, location, worker_user.worker_profile)

    response = client.post(
        '/api/operations/bulk-publish/',
        {'ids': [str(local_shift.id), str(outside_shift.id)]},
        format='json',
    )
    assert response.status_code == 200
    assert response.json()['published'] == 1
    local_shift.refresh_from_db()
    outside_shift.refresh_from_db()
    assert local_shift.status == Shift.Status.PUBLISHED
    assert outside_shift.status == Shift.Status.DRAFT
