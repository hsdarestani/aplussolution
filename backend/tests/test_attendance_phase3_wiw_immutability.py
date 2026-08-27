from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.attendance_models import TimeEntryCorrection
from core.models import TimeEntry


@pytest.mark.django_db
def test_worker_sees_imported_wiw_history_but_cannot_request_correction(worker_user, shift):
    original_in = timezone.now() - timedelta(days=20, hours=5)
    original_out = timezone.now() - timedelta(days=20, hours=1)
    entry = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=original_in,
        clock_out=original_out,
        approved=False,
        wiw_time_id='wiw-readonly-history-1',
        wiw_payload={'source': 'when_i_work'},
    )

    worker = APIClient(); worker.force_authenticate(worker_user)
    home = worker.get('/api/attendance/home/')

    assert home.status_code == 200
    history = [row for row in home.data['history'] if row['id'] == str(entry.id)]
    assert len(history) == 1
    assert history[0]['wiw_time_id'] == 'wiw-readonly-history-1'

    response = worker.post(
        f'/api/attendance/entries/{entry.id}/correction/',
        {
            'clock_in': (original_in - timedelta(minutes=30)).isoformat(),
            'clock_out': original_out.isoformat(),
            'reason': 'Historischer Test darf nicht mutieren.',
        },
        format='json',
    )

    assert response.status_code == 400
    assert 'schreibgeschützte' in response.data['detail']
    assert not TimeEntryCorrection.objects.filter(entry=entry).exists()
    entry.refresh_from_db()
    assert entry.clock_in == original_in
    assert entry.clock_out == original_out
    assert entry.approved is False


@pytest.mark.django_db
def test_imported_wiw_correction_cannot_be_decided_and_is_not_active_worker_workflow(worker_user, manager_user, shift):
    original_in = timezone.now() - timedelta(days=30, hours=6)
    original_out = timezone.now() - timedelta(days=30, hours=1)
    entry = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=original_in,
        clock_out=original_out,
        approved=False,
        wiw_time_id='wiw-readonly-history-2',
    )
    correction = TimeEntryCorrection.objects.create(
        entry=entry,
        requested_by=worker_user.worker_profile,
        requested_clock_in=original_in - timedelta(hours=1),
        requested_clock_out=original_out,
        reason='Legacy correction from before Phase 2.',
    )

    worker = APIClient(); worker.force_authenticate(worker_user)
    home = worker.get('/api/attendance/home/')
    assert home.status_code == 200
    assert home.data['pending_corrections'] == 0
    assert all(row['id'] != str(correction.id) for row in home.data['corrections'])

    manager = APIClient(); manager.force_authenticate(manager_user)
    exceptions = manager.get('/api/attendance/exceptions/')
    assert exceptions.status_code == 200
    assert exceptions.data['counts']['pending_corrections'] == 0

    decision = manager.post(
        f'/api/attendance/corrections/{correction.id}/decide/',
        {'status': 'approved'},
        format='json',
    )
    assert decision.status_code == 400
    assert 'schreibgeschützte' in decision.data['detail']

    correction.refresh_from_db(); entry.refresh_from_db()
    assert correction.status == TimeEntryCorrection.Status.PENDING
    assert correction.decided_by is None
    assert correction.decided_at is None
    assert entry.clock_in == original_in
    assert entry.clock_out == original_out
    assert entry.approved is False


@pytest.mark.django_db
def test_admin_cannot_close_or_approve_imported_wiw_time_entry(worker_user, manager_user, shift):
    now = timezone.now()
    imported_open = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=now - timedelta(hours=20),
        clock_out=None,
        approved=False,
        wiw_time_id='wiw-readonly-open-3',
    )
    imported_closed = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=now - timedelta(days=5, hours=5),
        clock_out=now - timedelta(days=5, hours=1),
        approved=False,
        wiw_time_id='wiw-readonly-closed-4',
    )

    manager = APIClient(); manager.force_authenticate(manager_user)

    close = manager.post(
        f'/api/attendance/entries/{imported_open.id}/close/',
        {'reason': 'Dieser historische Timer soll unverändert bleiben.'},
        format='json',
    )
    assert close.status_code == 400
    assert 'schreibgeschützte' in close.data['detail']

    approve = manager.post(f'/api/time-entries/{imported_closed.id}/approve/', {}, format='json')
    assert approve.status_code == 400
    assert 'schreibgeschützte' in approve.data['detail']

    imported_open.refresh_from_db(); imported_closed.refresh_from_db()
    assert imported_open.clock_out is None
    assert imported_open.edit_reason == ''
    assert imported_closed.approved is False
    assert imported_closed.approved_by is None
