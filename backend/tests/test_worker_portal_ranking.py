import pytest

from core.models import User, WorkerProfile


@pytest.mark.django_db
def test_worker_ranking_shows_active_workers_without_sensitive_profile_fields(auth_worker, worker_user, second_worker):
    worker_user.worker_profile.ranking_points = 12
    worker_user.worker_profile.save(update_fields=['ranking_points'])
    second_worker.ranking_points = 30
    second_worker.save(update_fields=['ranking_points'])

    response = auth_worker.get('/api/employee/ranking/')

    assert response.status_code == 200
    assert [row['employee_number'] for row in response.data] == ['MA-002', 'MA-001']
    assert response.data[0]['ranking_points'] == 30
    assert response.data[1]['is_current_user'] is True

    payload = str(response.data).lower()
    for forbidden in ('email', 'tariff_hourly_rate', 'extra_allowance', 'monthly_hours', 'iban', 'phone'):
        assert forbidden not in payload


@pytest.mark.django_db
def test_normal_workers_endpoint_remains_self_scoped(auth_worker, worker_user, second_worker):
    response = auth_worker.get('/api/workers/')

    assert response.status_code == 200
    rows = response.data['results'] if isinstance(response.data, dict) and 'results' in response.data else response.data
    assert [row['id'] for row in rows] == [str(worker_user.worker_profile.id)]
    assert str(second_worker.id) not in {row['id'] for row in rows}


@pytest.mark.django_db
def test_client_cannot_open_employee_ranking(auth_client):
    response = auth_client.get('/api/employee/ranking/')
    assert response.status_code == 403


@pytest.mark.django_db
def test_inactive_and_synthetic_workers_are_excluded(auth_worker, worker_user):
    inactive_user = User.objects.create_user('inactive@example.com', 'StrongPass123!', first_name='Inactive', role=User.Role.WORKER)
    WorkerProfile.objects.create(user=inactive_user, employee_number='MA-INACTIVE', employment_type='minijob', active=False, ranking_points=999)
    synthetic_user = User.objects.create_user('legacy@sync.invalid', 'StrongPass123!', first_name='Legacy', role=User.Role.WORKER)
    WorkerProfile.objects.create(user=synthetic_user, employee_number='MA-SYNC', employment_type='minijob', active=True, ranking_points=999)

    response = auth_worker.get('/api/employee/ranking/')

    assert response.status_code == 200
    employee_numbers = {row['employee_number'] for row in response.data}
    assert 'MA-INACTIVE' not in employee_numbers
    assert 'MA-SYNC' not in employee_numbers
