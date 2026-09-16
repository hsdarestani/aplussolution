from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import TimeEntry


@pytest.mark.django_db
def test_worker_can_clock_in_and_out_when_location_has_no_gps(auth_worker, worker_user, shift):
    now = timezone.now()
    shift.starts_at = now - timedelta(minutes=5)
    shift.ends_at = now + timedelta(hours=4)
    shift.location.latitude = None
    shift.location.longitude = None
    shift.location.save(update_fields=['latitude', 'longitude', 'updated_at'])
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])

    clocked_in = auth_worker.post(
        '/api/time-entries/clock_in/',
        {'shift': str(shift.id)},
        format='json',
    )

    assert clocked_in.status_code == 201
    entry = TimeEntry.objects.get(worker=worker_user.worker_profile, wiw_time_id__isnull=True)
    assert entry.clock_in_lat is None
    assert entry.clock_in_lng is None

    clocked_out = auth_worker.post('/api/time-entries/clock_out/', {}, format='json')

    assert clocked_out.status_code == 200
    assert clocked_out.data['review_required'] is False
    entry.refresh_from_db()
    assert entry.clock_out is not None
    assert entry.clock_out_lat is None
    assert entry.clock_out_lng is None
    assert entry.approved is True
