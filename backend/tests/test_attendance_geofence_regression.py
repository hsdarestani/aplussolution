from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import TimeEntry


def _put_shift_in_clock_window(shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(minutes=5)
    shift.ends_at = now + timedelta(hours=4)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])


@pytest.mark.django_db
def test_configured_geofence_still_requires_employee_location(auth_worker, worker_user, shift):
    _put_shift_in_clock_window(shift)

    response = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id)},
        format='json',
    )

    assert response.status_code == 400
    assert 'Standortfreigabe' in response.data['detail']
    assert not TimeEntry.objects.filter(worker=worker_user.worker_profile, wiw_time_id__isnull=True).exists()


@pytest.mark.django_db
def test_configured_geofence_still_rejects_clock_in_outside_radius(auth_worker, worker_user, shift):
    _put_shift_in_clock_window(shift)

    response = auth_worker.post(
        '/api/time-entries/clock_in/',
        {
            'shift': str(shift.id),
            'lat': 51.0,
            'lng': 9.0,
        },
        format='json',
    )

    assert response.status_code == 400
    assert 'vom Einsatzort entfernt' in response.data['detail']
    assert 'Erlaubt sind 250 m' in response.data['detail']
    assert not TimeEntry.objects.filter(worker=worker_user.worker_profile, wiw_time_id__isnull=True).exists()


@pytest.mark.django_db
def test_configured_geofence_keeps_normal_clock_in_and_out_behavior(auth_worker, worker_user, shift):
    _put_shift_in_clock_window(shift)

    clocked_in = auth_worker.post(
        '/api/time-entries/clock_in/',
        {
            'shift': str(shift.id),
            'lat': 50.1100,
            'lng': 8.6800,
        },
        format='json',
    )
    assert clocked_in.status_code == 201, clocked_in.data

    entry = TimeEntry.objects.get(worker=worker_user.worker_profile, wiw_time_id__isnull=True)
    assert float(entry.clock_in_lat) == pytest.approx(50.1100)
    assert float(entry.clock_in_lng) == pytest.approx(8.6800)

    clocked_out = auth_worker.post(
        '/api/time-entries/clock_out/',
        {'lat': 50.1100, 'lng': 8.6800},
        format='json',
    )
    assert clocked_out.status_code == 200, clocked_out.data
    assert clocked_out.data['review_required'] is False

    entry.refresh_from_db()
    assert entry.clock_out is not None
    assert float(entry.clock_out_lat) == pytest.approx(50.1100)
    assert float(entry.clock_out_lng) == pytest.approx(8.6800)
    assert entry.approved is True


@pytest.mark.django_db
def test_configured_geofence_still_routes_offsite_clock_out_to_review(auth_worker, worker_user, shift):
    _put_shift_in_clock_window(shift)

    clocked_in = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id), 'lat': 50.1100, 'lng': 8.6800},
        format='json',
    )
    assert clocked_in.status_code == 201, clocked_in.data

    clocked_out = auth_worker.post(
        '/api/time-entries/clock_out/',
        {'lat': 51.0, 'lng': 9.0},
        format='json',
    )
    assert clocked_out.status_code == 200, clocked_out.data
    assert clocked_out.data['review_required'] is True
    assert 'vom Einsatzort entfernt' in clocked_out.data['review_reason']

    entry = TimeEntry.objects.get(worker=worker_user.worker_profile, wiw_time_id__isnull=True)
    assert entry.clock_out is not None
    assert entry.approved is False
    assert entry.edit_reason.startswith('OUTSIDE_GEOFENCE:')
