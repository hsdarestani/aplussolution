from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from core.wiw import WhenIWorkClient, WhenIWorkError
from core.wiw_dashboard import _as_datetime, _live_wiw_snapshot, _pending, _request_bucket


def test_wiw_request_bucket_covers_dashboard_categories():
    assert _request_bucket({'type': 'time_off', 'status': 'pending'}) == 'time_off_requests'
    assert _request_bucket({'request_type': 'open_shift_pickup', 'status': 'pending'}) == 'open_shift_requests'
    assert _request_bucket({'kind': 'shift_swap', 'status': 'pending'}) == 'shift_requests'
    assert _request_bucket({'shift_id': 123, 'status': 'pending'}) == 'shift_requests'
    assert _request_bucket({'type': 'other', 'status': 'pending'}) is None


def test_wiw_request_pending_filter_and_flexible_datetime():
    assert _pending({'status': 'pending'}) is True
    assert _pending({'status': 'approved'}) is False
    parsed = _as_datetime('Tue, 28 Jul 2026 16:00:00 +0200')
    assert parsed is not None
    assert timezone.is_aware(parsed)


def test_live_wiw_snapshot_counts_open_shifts_and_pending_requests(settings):
    cache.clear()
    settings.WIW_DEV_KEY = 'dev'
    settings.WIW_EMAIL = 'api@example.com'
    settings.WIW_PASSWORD = 'secret'
    now = timezone.now()
    shifts = [
        {'id': 1, 'user_id': None, 'status': 'published', 'end_time': (now + timedelta(hours=2)).isoformat()},
        {'id': 2, 'user_id': 99, 'status': 'published', 'end_time': (now + timedelta(hours=2)).isoformat()},
        {'id': 3, 'user_id': None, 'status': 'cancelled', 'end_time': (now + timedelta(hours=2)).isoformat()},
        {'id': 4, 'user_id': None, 'status': 'published', 'end_time': (now - timedelta(hours=2)).isoformat()},
    ]
    requests = [
        {'id': 10, 'type': 'time_off', 'status': 'pending'},
        {'id': 11, 'type': 'open_shift_pickup', 'status': 'pending'},
        {'id': 12, 'type': 'shift_swap', 'status': 'pending'},
        {'id': 13, 'type': 'shift_swap', 'status': 'approved'},
        {'id': 14, 'type': 'mystery', 'status': 'pending'},
    ]

    fake = SimpleNamespace()
    fake.collection = lambda name, optional=False: SimpleNamespace(items=shifts if name == 'shifts' else requests)
    with patch('core.wiw_dashboard.WhenIWorkClient', return_value=fake):
        result = _live_wiw_snapshot(now)

    assert result['open_shifts_available'] == 1
    assert result['time_off_requests'] == 1
    assert result['open_shift_requests'] == 1
    assert result['shift_requests'] == 1
    assert result['wiw_open_requests_unclassified'] == 1
    assert result['source'] == 'wiw-live-readonly'


@pytest.mark.django_db
def test_mobile_dashboard_has_local_fallback(auth_admin, settings):
    settings.WIW_SYNC_ENABLED = False
    response = auth_admin.get('/api/admin/mobile-dashboard/')
    assert response.status_code == 200
    assert response.data['source'] == 'aplus-local'
    assert response.data['sync_enabled'] is False
    assert 'open_shifts_available' in response.data
    assert 'open_shift_requests' in response.data


def test_wiw_client_blocks_writes_in_read_only_mode(settings):
    settings.WIW_DEV_KEY = 'dev'
    settings.WIW_EMAIL = 'api@example.com'
    settings.WIW_PASSWORD = 'secret'
    settings.WIW_USER_ID = '1'
    settings.WIW_READ_ONLY = True
    client = WhenIWorkClient()
    with pytest.raises(WhenIWorkError, match='schreibgeschützte'):
        client.post('/shifts', {'id': 1})
