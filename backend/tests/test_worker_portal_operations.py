from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Availability, Shift, User, WorkerProfile


@pytest.mark.django_db
def test_worker_operations_do_not_expose_peer_email(auth_worker, worker_user):
    peer_user = User.objects.create_user(
        'private.peer@example.com',
        'StrongPass123!',
        role=User.Role.WORKER,
        is_onboarded=True,
    )
    WorkerProfile.objects.create(
        user=peer_user,
        employee_number='MA-PRIVATE',
        employment_type='minijob',
    )

    response = auth_worker.get('/api/operations/')

    assert response.status_code == 200
    candidate = next(row for row in response.data['swap_candidates'] if row['id'] != str(worker_user.worker_profile.id))
    assert candidate['name'] == 'MA-PRIVATE'
    assert 'private.peer@example.com' not in str(response.data)


@pytest.mark.django_db
def test_worker_cannot_delete_other_workers_availability(auth_worker, second_worker):
    item = Availability.objects.create(
        worker=second_worker,
        starts_at=timezone.now() + timedelta(days=1),
        ends_at=timezone.now() + timedelta(days=1, hours=4),
        available=False,
    )

    response = auth_worker.delete(f'/api/operations/availability/{item.id}/')

    assert response.status_code == 403
    assert Availability.objects.filter(pk=item.id).exists()


@pytest.mark.django_db
def test_worker_can_delete_own_availability(auth_worker, worker_user):
    item = Availability.objects.create(
        worker=worker_user.worker_profile,
        starts_at=timezone.now() + timedelta(days=1),
        ends_at=timezone.now() + timedelta(days=1, hours=4),
        available=True,
    )

    response = auth_worker.delete(f'/api/operations/availability/{item.id}/')

    assert response.status_code == 204
    assert not Availability.objects.filter(pk=item.id).exists()


@pytest.mark.django_db
def test_worker_cannot_request_swap_for_another_workers_shift(auth_worker, second_worker, company, location, position):
    starts = timezone.now() + timedelta(days=2)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=second_worker,
        starts_at=starts,
        ends_at=starts + timedelta(hours=6),
        status=Shift.Status.CONFIRMED,
    )

    response = auth_worker.post('/api/operations/swaps/', {'shift': str(shift.id)}, format='json')

    assert response.status_code == 403


@pytest.mark.django_db
def test_swap_target_must_be_active_real_worker(auth_worker, shift):
    synthetic_user = User.objects.create_user(
        'legacy.swap@sync.invalid',
        'StrongPass123!',
        role=User.Role.WORKER,
        is_onboarded=True,
    )
    synthetic = WorkerProfile.objects.create(
        user=synthetic_user,
        employee_number='MA-SYNTHETIC',
        employment_type='minijob',
        active=True,
    )

    response = auth_worker.post(
        '/api/operations/swaps/',
        {'shift': str(shift.id), 'offered_to': str(synthetic.id)},
        format='json',
    )

    assert response.status_code == 404
