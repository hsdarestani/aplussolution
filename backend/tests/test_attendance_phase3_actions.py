from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Notification, TimeEntry, User, WorkerProfile


@pytest.mark.django_db
def test_worker_cannot_clock_in_without_owned_shift():
    user = User.objects.create_user(
        'phase3-noschedule@example.com',
        'StrongPass123!',
        first_name='No',
        last_name='Schedule',
        role=User.Role.WORKER,
        is_onboarded=True,
    )
    WorkerProfile.objects.create(user=user, employee_number='PHASE3-NO-SHIFT')
    client = APIClient(); client.force_authenticate(user)
    response = client.post('/api/time-entries/clock_in/', {}, format='json')
    assert response.status_code == 400
    assert 'keine passende bestätigte Schicht' in str(response.data)
    assert TimeEntry.objects.count() == 0


@pytest.mark.django_db
def test_manager_can_close_long_running_timer_with_reason(worker_user, manager_user, shift):
    entry = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=timezone.now() - timedelta(hours=13),
        clock_out=None,
        approved=False,
    )
    manager = APIClient(); manager.force_authenticate(manager_user)
    response = manager.post(
        f'/api/attendance/entries/{entry.id}/close/',
        {'reason': 'Mitarbeiter hat das Ausstempeln vergessen.'},
        format='json',
    )
    assert response.status_code == 200
    entry.refresh_from_db()
    assert entry.clock_out is not None
    assert entry.approved is False
    assert entry.approved_by is None
    assert 'vergessen' in entry.edit_reason
    assert Notification.objects.filter(user=worker_user, kind=f'time-entry-admin-closed-{entry.id}').exists()


@pytest.mark.django_db
def test_worker_cannot_close_running_entry(worker_user, shift):
    entry = TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        shift=shift,
        clock_in=timezone.now() - timedelta(hours=13),
        clock_out=None,
    )
    worker = APIClient(); worker.force_authenticate(worker_user)
    response = worker.post(
        f'/api/attendance/entries/{entry.id}/close/',
        {'reason': 'Should not be allowed.'},
        format='json',
    )
    assert response.status_code == 403
