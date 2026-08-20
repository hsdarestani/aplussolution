from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import TimeEntry, User, WorkerProfile


@pytest.mark.django_db
def test_operations_overview_ignores_imported_time_history_and_synthetic_workers(auth_admin, worker_user):
    now = timezone.now()
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        clock_in=now - timedelta(hours=3),
        clock_out=now - timedelta(hours=1),
        approved=False,
    )
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        clock_in=now - timedelta(days=2),
        clock_out=now - timedelta(days=2) + timedelta(hours=5),
        approved=False,
        wiw_time_id='legacy-operations-complete',
    )
    TimeEntry.objects.create(
        worker=worker_user.worker_profile,
        clock_in=now - timedelta(days=2),
        clock_out=None,
        approved=False,
        wiw_time_id='legacy-operations-open',
    )

    synthetic_user = User.objects.create(
        email='wiw-operations@sync.invalid',
        role=User.Role.WORKER,
        is_active=True,
    )
    synthetic_user.set_unusable_password(); synthetic_user.save()
    synthetic_worker = WorkerProfile.objects.create(
        user=synthetic_user,
        employee_number='WIW-OPERATIONS',
        active=True,
        wiw_user_id='operations-only',
    )
    TimeEntry.objects.create(
        worker=synthetic_worker,
        clock_in=now - timedelta(hours=4),
        clock_out=now - timedelta(hours=1),
        approved=False,
    )

    response = auth_admin.get('/api/operations/')

    assert response.status_code == 200
    assert response.data['unapproved_time_entries'] == 1
    assert response.data['missing_clock_outs'] == 0
    assert response.data['active_workers'] == 1
    assert all(item['id'] != str(synthetic_worker.id) for item in response.data['swap_candidates'])
