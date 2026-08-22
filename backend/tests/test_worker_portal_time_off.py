from datetime import date, timedelta

import pytest

from core.models import TimeOffRequest


@pytest.mark.django_db
def test_worker_cannot_self_approve_time_off(auth_worker, worker_user):
    start = date.today() + timedelta(days=5)
    response = auth_worker.post(
        '/api/time-off/',
        {
            'starts_on': start.isoformat(),
            'ends_on': (start + timedelta(days=2)).isoformat(),
            'reason': 'Urlaub',
            'status': 'approved',
        },
        format='json',
    )

    assert response.status_code == 201
    request = TimeOffRequest.objects.get(pk=response.data['id'])
    assert request.worker_id == worker_user.worker_profile.id
    assert request.status == TimeOffRequest.Status.PENDING
    assert request.decided_by_id is None


@pytest.mark.django_db
def test_time_off_rejects_end_before_start(auth_worker):
    start = date.today() + timedelta(days=5)
    response = auth_worker.post(
        '/api/time-off/',
        {
            'starts_on': start.isoformat(),
            'ends_on': (start - timedelta(days=1)).isoformat(),
            'reason': 'Ungültiger Zeitraum',
        },
        format='json',
    )

    assert response.status_code == 400
    assert TimeOffRequest.objects.count() == 0


@pytest.mark.django_db
def test_worker_cannot_approve_existing_time_off(auth_worker, worker_user):
    start = date.today() + timedelta(days=5)
    request = TimeOffRequest.objects.create(
        worker=worker_user.worker_profile,
        starts_on=start,
        ends_on=start + timedelta(days=1),
        status=TimeOffRequest.Status.PENDING,
    )

    response = auth_worker.patch(
        f'/api/time-off/{request.id}/',
        {'status': 'approved'},
        format='json',
    )

    assert response.status_code == 403
    request.refresh_from_db()
    assert request.status == TimeOffRequest.Status.PENDING
