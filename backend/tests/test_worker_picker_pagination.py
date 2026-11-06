"""The mobile shift picker must receive employees after the default 50-row page."""

import pytest

from core.models import User, WorkerProfile


@pytest.mark.django_db
def test_workers_directory_includes_late_alphabetical_service_worker(auth_admin):
    for index in range(55):
        user = User.objects.create(
            email=f'picker-{index:03d}@example.test',
            first_name='Test', last_name=f'Name{index:03d}',
            role=User.Role.WORKER,
        )
        WorkerProfile.objects.create(
            user=user, employee_number=f'PICKER-{index:03d}',
            active=True, schedule_groups=['service'],
        )

    late = User.objects.create(
        email='picker-last@example.test',
        first_name='Test', last_name='Wilke', role=User.Role.WORKER,
    )
    WorkerProfile.objects.create(
        user=late, employee_number='PICKER-LAST',
        active=True, schedule_groups=['service'],
    )

    response = auth_admin.get('/api/workers/?ordering=user__last_name')
    assert response.status_code == 200
    rows = response.data['results'] if isinstance(response.data, dict) else response.data
    assert len(rows) == 56
    assert rows[-1]['user_detail']['name'] == 'Test Wilke'
    assert rows[-1]['schedule_groups'] == ['service']
