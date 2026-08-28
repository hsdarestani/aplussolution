from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import TimeEntry


@pytest.mark.django_db
def test_worker_attendance_home_returns_complete_imported_wiw_history(auth_worker, worker_user, shift):
    now = timezone.now()
    created = []
    for index in range(35):
        clock_in = now - timedelta(days=index + 40, hours=8)
        entry = TimeEntry.objects.create(
            worker=worker_user.worker_profile,
            shift=shift,
            clock_in=clock_in,
            clock_out=clock_in + timedelta(hours=7),
            break_minutes=30,
            approved=True,
            wiw_time_id=f'full-history-{index}',
            wiw_synced_at=now,
        )
        created.append(entry)

    response = auth_worker.get('/api/attendance/home/')

    assert response.status_code == 200
    assert len(response.data['history']) == 35
    history_ids = {row['id'] for row in response.data['history']}
    assert str(created[-1].id) in history_ids
    assert all(row['wiw_time_id'] for row in response.data['history'])


@pytest.mark.django_db
def test_attendance_history_archive_is_role_scoped(auth_admin, auth_worker, auth_client, worker_user, shift):
    now = timezone.now()
    for index in range(3):
        clock_in = now - timedelta(days=500 + index)
        TimeEntry.objects.create(
            worker=worker_user.worker_profile,
            shift=shift,
            clock_in=clock_in,
            clock_out=clock_in + timedelta(hours=6),
            approved=True,
            wiw_time_id=f'archive-{index}',
            wiw_synced_at=now,
        )

    worker = auth_worker.get('/api/attendance/history/')
    assert worker.status_code == 200
    assert worker.data['count'] == 3
    assert len(worker.data['history']) == 3
    assert {row['worker'] for row in worker.data['history']} == {str(worker_user.worker_profile.id)}

    admin = auth_admin.get('/api/attendance/history/')
    assert admin.status_code == 200
    assert admin.data['count'] >= 3
    assert any(row['wiw_time_id'] == 'archive-2' for row in admin.data['history'])

    client = auth_client.get('/api/attendance/history/')
    assert client.status_code == 403
