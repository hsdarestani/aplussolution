from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Availability, Notification, Shift, ShiftSwapRequest, TimeEntry, User, WorkerProfile


def published_shift(company, location, position, start, required_count=1):
    return Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=4),
        status=Shift.Status.PUBLISHED,
        is_open=True,
        required_count=required_count,
    )


@pytest.mark.django_db
def test_overlap_blocks_worker_claim(auth_worker, shift, company, location, position):
    candidate = published_shift(company, location, position, shift.starts_at + timedelta(minutes=30))
    response = auth_worker.post(f'/api/shifts/{candidate.id}/claim/', {}, format='json')
    assert response.status_code == 400
    assert 'bereits eine Schicht' in str(response.data)


@pytest.mark.django_db
def test_unavailability_blocks_worker_claim(auth_worker, worker_user, company, location, position):
    start = timezone.now() + timedelta(days=1)
    Availability.objects.create(
        worker=worker_user.worker_profile,
        starts_at=start,
        ends_at=start + timedelta(hours=8),
        available=False,
    )
    candidate = published_shift(company, location, position, start)
    response = auth_worker.post(f'/api/shifts/{candidate.id}/claim/', {}, format='json')
    assert response.status_code == 400
    assert 'nicht verfügbar' in str(response.data)


@pytest.mark.django_db
def test_worker_claim_requires_admin_approval_before_release(auth_worker, auth_admin, worker_user, company, location, position):
    start = timezone.now() + timedelta(days=2)
    candidate = published_shift(company, location, position, start)
    response = auth_worker.post(f'/api/shifts/{candidate.id}/claim/', {}, format='json')
    assert response.status_code == 200
    candidate.refresh_from_db()
    assert candidate.worker == worker_user.worker_profile
    assert candidate.is_open is False

    # The legacy direct-release path must no longer let an employee silently
    # give back an already accepted shift.
    direct_release = auth_worker.post(f'/api/shifts/{candidate.id}/release/', {}, format='json')
    assert direct_release.status_code == 400
    candidate.refresh_from_db()
    assert candidate.worker == worker_user.worker_profile
    assert candidate.is_open is False

    requested = auth_worker.post(f'/api/employee/shifts/{candidate.id}/release-request/', {}, format='json')
    assert requested.status_code == 202
    assert requested.data['pending_approval'] is True

    candidate.refresh_from_db()
    assert candidate.worker == worker_user.worker_profile
    assert candidate.is_open is False

    pending = auth_admin.get('/api/premium/release-requests/')
    assert pending.status_code == 200
    row = next(item for item in pending.data if str(item['shift_id']) == str(candidate.id))
    approved = auth_admin.post(f"/api/premium/release-requests/{row['id']}/decide/", {'status': 'approved'}, format='json')
    assert approved.status_code == 200
    assert approved.data['status'] == 'approved'

    candidate.refresh_from_db()
    assert candidate.worker is None
    assert candidate.is_open is True


@pytest.mark.django_db
def test_multi_place_shift_accepts_exact_capacity(company, location, position):
    start = timezone.now() + timedelta(days=3)
    candidate = published_shift(company, location, position, start, required_count=3)
    users = []
    for index in range(4):
        user = User.objects.create_user(
            f'capacity{index}@example.com',
            'StrongPass123!',
            first_name=f'Test{index}',
            role=User.Role.WORKER,
            is_onboarded=True,
        )
        WorkerProfile.objects.create(user=user, employee_number=f'CAP-{index}')
        users.append(user)
    for user in users[:3]:
        client = APIClient(); client.force_authenticate(user)
        response = client.post(f'/api/shifts/{candidate.id}/claim/', {}, format='json')
        assert response.status_code == 200
    fourth = APIClient(); fourth.force_authenticate(users[3])
    response = fourth.post(f'/api/shifts/{candidate.id}/claim/', {}, format='json')
    assert response.status_code == 400
    assert 'vollständig besetzt' in str(response.data) or 'nicht zur Übernahme' in str(response.data)


@pytest.mark.django_db
def test_geofence_clock_in_and_out(auth_worker, worker_user, shift):
    shift.starts_at = timezone.now() - timedelta(minutes=10)
    shift.ends_at = timezone.now() + timedelta(hours=4)
    shift.save()
    outside = auth_worker.post('/api/time-entries/clock_in/', {'shift': str(shift.id), 'lat': 51, 'lng': 9}, format='json')
    assert outside.status_code == 400
    inside = auth_worker.post('/api/time-entries/clock_in/', {'shift': str(shift.id), 'lat': 50.1101, 'lng': 8.6801}, format='json')
    assert inside.status_code == 201
    out = auth_worker.post('/api/time-entries/clock_out/', {'lat': 50.1101, 'lng': 8.6801}, format='json')
    assert out.status_code == 200
    assert TimeEntry.objects.get().clock_out is not None

