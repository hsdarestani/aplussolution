from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Location, Shift, TimeEntry, User, WorkerProfile


@pytest.mark.django_db
def test_admin_can_assign_multiple_workers_to_staffing_slots(
    auth_admin, worker_user, second_worker, company, location, position
):
    starts_at = timezone.now() + timedelta(days=1)
    response = auth_admin.post(
        '/api/shifts/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': starts_at.isoformat(),
            'ends_at': (starts_at + timedelta(hours=2)).isoformat(),
            'required_count': 2,
            'break_minutes': 0,
            'status': 'draft',
        },
        format='json',
    )
    assert response.status_code == 201, response.data
    shift_id = response.data['id']

    response = auth_admin.post(
        f'/api/shifts/{shift_id}/assign/',
        {
            'workers': [str(worker_user.worker_profile.id), str(second_worker.id)],
            'publish_remaining': True,
        },
        format='json',
    )
    assert response.status_code == 200, response.data
    assert response.data['filled_count'] == 2
    assert response.data['open_count'] == 0
    assert response.data['status'] == 'confirmed'
    assert {item['id'] for item in response.data['assigned_workers']} == {
        str(worker_user.worker_profile.id),
        str(second_worker.id),
    }


@pytest.mark.django_db
def test_partial_admin_assignment_keeps_remaining_slot_open(
    auth_admin, worker_user, company, location, position
):
    starts_at = timezone.now() + timedelta(days=2)
    response = auth_admin.post(
        '/api/shifts/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': starts_at.isoformat(),
            'ends_at': (starts_at + timedelta(hours=2)).isoformat(),
            'required_count': 2,
            'break_minutes': 0,
            'status': 'draft',
        },
        format='json',
    )
    assert response.status_code == 201, response.data

    response = auth_admin.post(
        f"/api/shifts/{response.data['id']}/assign/",
        {
            'workers': [str(worker_user.worker_profile.id)],
            'publish_remaining': True,
        },
        format='json',
    )
    assert response.status_code == 200, response.data
    assert response.data['filled_count'] == 1
    assert response.data['open_count'] == 1
    assert response.data['status'] == 'published'


@pytest.mark.django_db
def test_admin_cannot_assign_synthetic_migration_worker(
    auth_admin, company, location, position
):
    synthetic_user = User.objects.create(email='wiw-assignment@sync.invalid', role=User.Role.WORKER, is_active=True)
    synthetic_user.set_unusable_password(); synthetic_user.save()
    synthetic_worker = WorkerProfile.objects.create(
        user=synthetic_user,
        employee_number='WIW-ASSIGNMENT',
        active=True,
        wiw_user_id='assignment-only',
    )
    starts_at = timezone.now() + timedelta(days=3)
    created = auth_admin.post(
        '/api/shifts/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': starts_at.isoformat(),
            'ends_at': (starts_at + timedelta(hours=2)).isoformat(),
            'required_count': 1,
            'break_minutes': 0,
            'status': 'draft',
        },
        format='json',
    )
    assert created.status_code == 201, created.data

    assigned = auth_admin.post(
        f"/api/shifts/{created.data['id']}/assign/",
        {'workers': [str(synthetic_worker.id)], 'publish_remaining': True},
        format='json',
    )

    assert assigned.status_code == 400
    assert 'Migrationsdatensatz' in assigned.data['detail']


@pytest.mark.django_db
def test_clock_in_rejects_shift_without_configured_geofence(
    auth_worker, worker_user, company, position
):
    location = Location.objects.create(
        client=company,
        name='Ohne GPS',
        address='Teststraße 1, Frankfurt',
        latitude=None,
        longitude=None,
        geofence_radius_m=250,
    )
    starts_at = timezone.now() - timedelta(minutes=10)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker_user.worker_profile,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=2),
        status=Shift.Status.CONFIRMED,
    )

    response = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id), 'lat': 50.11, 'lng': 8.68},
        format='json',
    )
    assert response.status_code == 400
    assert 'GPS-Position' in response.data['detail']
    assert not TimeEntry.objects.filter(worker=worker_user.worker_profile).exists()
