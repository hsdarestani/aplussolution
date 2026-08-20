from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.attendance_models import TimeEntryCorrection
from core.models import Notification, TimeEntry, User, WorkerProfile


@pytest.mark.django_db
def test_worker_attendance_home_tracks_active_timer_and_history(auth_worker, worker_user, shift):
    shift.starts_at = timezone.now() - timedelta(minutes=5)
    shift.ends_at = timezone.now() + timedelta(hours=4)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])

    clocked = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id), 'lat': 50.1100, 'lng': 8.6800},
        format='json',
    )
    assert clocked.status_code == 201

    home = auth_worker.get('/api/attendance/home/')
    assert home.status_code == 200
    assert home.data['active_entry']['id'] == str(TimeEntry.objects.get().id)
    assert home.data['stale_active_entry'] is None
    assert home.data['eligible_shift']['id'] == str(shift.id)

    clocked_out = auth_worker.post(
        '/api/time-entries/clock_out/',
        {'lat': 50.1100, 'lng': 8.6800},
        format='json',
    )
    assert clocked_out.status_code == 200

    home = auth_worker.get('/api/attendance/home/')
    assert home.data['active_entry'] is None
    assert home.data['stale_active_entry'] is None
    assert home.data['history'][0]['id'] == str(TimeEntry.objects.get().id)


@pytest.mark.django_db
def test_worker_home_marks_old_open_timer_as_stale_and_does_not_count_it(worker_user, shift):
    now = timezone.now()
    stale = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=now - timedelta(hours=20),
        clock_out=None,
        approved=False,
    )
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=now - timedelta(hours=3),
        clock_out=now - timedelta(hours=1),
        approved=True,
    )

    worker = APIClient(); worker.force_authenticate(worker_user)
    response = worker.get('/api/attendance/home/')

    assert response.status_code == 200
    assert response.data['active_entry'] is None
    assert response.data['stale_active_entry']['id'] == str(stale.id)
    assert response.data['eligible_shift'] is None
    assert response.data['month_worked_minutes'] == 120


@pytest.mark.django_db
def test_worker_requests_correction_and_manager_approves(worker_user, manager_user, shift):
    original_in = timezone.now() - timedelta(hours=5)
    original_out = timezone.now() - timedelta(hours=1)
    entry = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=original_in,
        clock_out=original_out,
        approved=False,
    )

    worker_client = APIClient(); worker_client.force_authenticate(worker_user)
    requested_in = original_in - timedelta(minutes=30)
    response = worker_client.post(
        f'/api/attendance/entries/{entry.id}/correction/',
        {
            'clock_in': requested_in.isoformat(),
            'clock_out': original_out.isoformat(),
            'reason': 'Der tatsächliche Arbeitsbeginn war früher.',
        },
        format='json',
    )
    assert response.status_code == 201
    correction = TimeEntryCorrection.objects.get()
    assert correction.status == TimeEntryCorrection.Status.PENDING
    assert Notification.objects.filter(kind=f'time-correction-{correction.id}').exists()

    manager = APIClient(); manager.force_authenticate(manager_user)
    exceptions = manager.get('/api/attendance/exceptions/')
    assert exceptions.status_code == 200
    assert exceptions.data['counts']['pending_corrections'] == 1

    decision = manager.post(
        f'/api/attendance/corrections/{correction.id}/decide/',
        {'status': 'approved', 'note': 'Plausibel geprüft.'},
        format='json',
    )
    assert decision.status_code == 200
    entry.refresh_from_db(); correction.refresh_from_db()
    assert entry.clock_in == requested_in
    assert entry.approved is True
    assert entry.approved_by == manager_user
    assert correction.status == TimeEntryCorrection.Status.APPROVED
    assert Notification.objects.filter(user=worker_user, kind=f'time-correction-decision-{correction.id}').exists()


@pytest.mark.django_db
def test_manager_exception_inbox_only_surfaces_attention_items(worker_user, manager_user, shift):
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=timezone.now() - timedelta(hours=4),
        clock_out=timezone.now() - timedelta(hours=1),
        approved=False,
    )
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=timezone.now() - timedelta(hours=13),
        clock_out=None,
        approved=False,
    )

    manager = APIClient(); manager.force_authenticate(manager_user)
    response = manager.get('/api/attendance/exceptions/')
    assert response.status_code == 200
    assert response.data['counts']['unapproved_entries'] == 1
    assert response.data['counts']['long_running_entries'] == 1
    assert response.data['counts']['total'] == 2

    worker = APIClient(); worker.force_authenticate(worker_user)
    denied = worker.get('/api/attendance/exceptions/')
    assert denied.status_code == 403


@pytest.mark.django_db
def test_manager_exception_count_is_not_capped_by_display_limit(worker_user, manager_user, shift):
    now = timezone.now()
    TimeEntry.objects.bulk_create([
        TimeEntry(
            worker=worker_user.worker_profile,
            shift=shift,
            clock_in=now - timedelta(days=2, minutes=index),
            clock_out=now - timedelta(days=2, minutes=index - 30),
            approved=False,
        )
        for index in range(105)
    ])

    manager = APIClient(); manager.force_authenticate(manager_user)
    response = manager.get('/api/attendance/exceptions/')

    assert response.status_code == 200
    assert response.data['counts']['unapproved_entries'] == 105
    assert response.data['list_limit'] == 100
    assert len(response.data['unapproved_entries']) == 100


@pytest.mark.django_db
def test_manager_exception_queue_ignores_synthetic_migration_workers(manager_user, shift):
    synthetic_user = User.objects.create_user(
        email='wiw-history-test@sync.invalid',
        password='temporary-password-123',
        first_name='Legacy',
        last_name='Import',
        role=User.Role.WORKER,
    )
    synthetic_worker = WorkerProfile.objects.create(
        user=synthetic_user,
        employee_number='WIW-HIST-TEST-1',
    )
    now = timezone.now()
    TimeEntry.objects.create(
        worker=synthetic_worker,
        shift=shift,
        clock_in=now - timedelta(days=4),
        clock_out=now - timedelta(days=4) + timedelta(hours=5),
        approved=False,
    )
    TimeEntry.objects.create(
        worker=synthetic_worker,
        shift=shift,
        clock_in=now - timedelta(days=4),
        clock_out=None,
        approved=False,
    )

    manager = APIClient(); manager.force_authenticate(manager_user)
    response = manager.get('/api/attendance/exceptions/')

    assert response.status_code == 200
    assert response.data['counts']['unapproved_entries'] == 0
    assert response.data['counts']['long_running_entries'] == 0
    assert response.data['counts']['total'] == 0
