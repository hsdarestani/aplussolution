from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from core.wiw import WhenIWorkClient, WhenIWorkError
from core.wiw_dashboard import _as_datetime, _live_wiw_snapshot, _pending


def test_wiw_request_pending_filter_and_flexible_datetime():
    assert _pending({'status': 'pending'}) is True
    assert _pending({'status': 'approved'}) is False
    assert _pending({'status': 0}) is True
    assert _pending({'status': 1}) is False
    parsed = _as_datetime('Tue, 28 Jul 2026 16:00:00 +0200')
    assert parsed is not None
    assert timezone.is_aware(parsed)


def test_live_wiw_snapshot_counts_open_shifts_and_dedicated_pending_requests(settings):
    cache.clear()
    settings.WIW_DEV_KEY = 'dev'
    settings.WIW_EMAIL = 'api@example.com'
    settings.WIW_PASSWORD = 'secret'
    now = timezone.now()

    class FakeClient:
        @staticmethod
        def extract_collection(payload, name='items'):
            return payload.get(name, []) if isinstance(payload, dict) else []

        def get(self, path, params=None):
            if path == '/shifts':
                return {'shifts': [
                    {'id': 1, 'user_id': 0, 'is_open': True, 'published': True, 'instances': 1, 'end_time': (now + timedelta(hours=2)).isoformat()},
                    {'id': 2, 'user_id': 99, 'is_open': False, 'published': True, 'end_time': (now + timedelta(hours=2)).isoformat()},
                    {'id': 3, 'user_id': 0, 'is_open': True, 'published': False, 'end_time': (now + timedelta(hours=2)).isoformat()},
                    {'id': 4, 'user_id': 0, 'is_open': True, 'published': True, 'end_time': (now - timedelta(hours=2)).isoformat()},
                ]}
            if path == '/requests':
                return {'requests': [{'id': 10, 'status': 0}], 'more': False}
            if path == '/swaps':
                return {'swaps': [{'id': 12, 'status': 0}], 'more': False}
            if path == '/openshiftapprovalrequests':
                return {'openshiftapprovalrequests': [{'id': 11, 'status': 0}, {'id': 13, 'status': 1}]}
            raise AssertionError(path)

    with patch('core.wiw_dashboard.WhenIWorkClient', return_value=FakeClient()):
        result = _live_wiw_snapshot(now)

    assert result['open_shifts_available'] == 1
    assert result['time_off_requests'] == 1
    assert result['open_shift_requests'] == 1
    assert result['shift_requests'] == 1
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
