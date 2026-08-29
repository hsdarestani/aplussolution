from datetime import timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from core import wiw_dashboard
from core.models import Shift
from core.wiw import WhenIWorkError


class FakeWhenIWorkClient:
    calls = []

    def __init__(self):
        type(self).calls = []

    @staticmethod
    def extract_collection(payload, name='items'):
        return payload.get(name, []) if isinstance(payload, dict) else []

    def get(self, path, params=None):
        params = dict(params or {})
        type(self).calls.append((path, params))
        if path == '/shifts':
            return {
                'shifts': [
                    {'id': 10, 'user_id': 0, 'is_open': True, 'published': True, 'instances': 16, 'start_time': (timezone.now() + timedelta(days=2, hours=-6)).isoformat(), 'end_time': (timezone.now() + timedelta(days=2)).isoformat(), 'position_name': 'Servicekraft', 'location_name': 'Marthas Finest'},
                    {'id': 11, 'user_id': 0, 'is_open': True, 'published': True, 'instances': 1, 'start_time': (timezone.now() + timedelta(days=3, hours=-6)).isoformat(), 'end_time': (timezone.now() + timedelta(days=3)).isoformat(), 'position_name': 'Servicekraft', 'location_name': 'Marthas Finest'},
                    {'id': 12, 'user_id': 99, 'is_open': False, 'published': True, 'instances': 50, 'end_time': (timezone.now() + timedelta(days=3)).isoformat()},
                ]
            }
        if path == '/requests':
            return {'requests': [{'id': 20, 'status': 0}], 'more': False}
        if path == '/swaps':
            return {'swaps': [{'id': 30, 'status': 0}], 'more': False}
        if path == '/openshiftapprovalrequests':
            return {
                'openshiftapprovalrequests': [
                    {'id': 40, 'status': 0},
                    {'id': 41, 'status': 1},
                ]
            }
        raise AssertionError(f'Unexpected path {path}')


@pytest.mark.django_db
def test_live_dashboard_uses_correct_wiw_resources_and_counts_instances(monkeypatch):
    cache.clear()
    monkeypatch.setattr(wiw_dashboard, 'WhenIWorkClient', FakeWhenIWorkClient)

    result = wiw_dashboard._live_wiw_snapshot(timezone.now())

    assert result['open_shifts_available'] == 17
    assert result['time_off_requests'] == 1
    assert result['shift_requests'] == 1
    assert result['open_shift_requests'] == 1
    assert result['source'] == 'wiw-live-readonly'
    assert result['live_error'] == ''

    calls = {path: params for path, params in FakeWhenIWorkClient.calls}
    assert calls['/shifts']['include_open'] == 'true'
    assert calls['/shifts']['include_onlyopen'] == 'true'
    assert calls['/shifts']['include_allopen'] == 'true'
    assert calls['/shifts']['all_locations'] == 'true'
    assert calls['/requests']['status'] == 0
    assert calls['/swaps']['status'] == 0
    assert calls['/swaps']['open_only'] == 'true'
    assert '/openshiftapprovalrequests' in calls


def test_numeric_wiw_request_statuses_are_not_all_treated_as_pending():
    assert wiw_dashboard._pending({'status': 0}) is True
    assert wiw_dashboard._pending({'user_status': 0, 'status': 2}) is True
    assert wiw_dashboard._pending({'status': 1}) is False
    assert wiw_dashboard._pending({'status': 4}) is False
    assert wiw_dashboard._pending({'status': 'pending'}) is True
    assert wiw_dashboard._pending({'status': 'approved'}) is False


@pytest.mark.django_db
def test_one_failed_wiw_resource_does_not_zero_other_live_counters(monkeypatch):
    class PartialClient(FakeWhenIWorkClient):
        def get(self, path, params=None):
            if path == '/openshiftapprovalrequests':
                raise WhenIWorkError('temporary upstream error')
            return super().get(path, params=params)

    cache.clear()
    monkeypatch.setattr(wiw_dashboard, 'WhenIWorkClient', PartialClient)

    result = wiw_dashboard._live_wiw_snapshot(timezone.now())

    assert result['open_shifts_available'] == 17
    assert result['time_off_requests'] == 1
    assert result['shift_requests'] == 1
    assert 'open_shift_requests' not in result
    assert result['source'] == 'wiw-live-partial'
    assert 'OpenShiftRequests' in result['live_error']


@pytest.mark.django_db
def test_local_open_shift_count_counts_native_capacity_cards(company, location, position):
    starts = timezone.now() + timedelta(days=4)
    Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts,
        ends_at=starts + timedelta(hours=6),
        required_count=2,
        status=Shift.Status.PUBLISHED,
    )

    assert wiw_dashboard._local_open_shift_count(timezone.now(), native_only=True) == 2


@pytest.mark.django_db
def test_mobile_dashboard_adds_native_open_shifts_to_live_wiw_count(monkeypatch, auth_admin, company, location, position):
    starts = timezone.now() + timedelta(days=5)
    Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts,
        ends_at=starts + timedelta(hours=6),
        required_count=1,
        status=Shift.Status.PUBLISHED,
    )
    monkeypatch.setattr(wiw_dashboard.settings, 'WIW_SYNC_ENABLED', True)
    monkeypatch.setattr(wiw_dashboard.settings, 'WIW_DEV_KEY', 'test-key', raising=False)
    monkeypatch.setattr(wiw_dashboard.settings, 'WIW_EMAIL', 'test@example.com', raising=False)
    monkeypatch.setattr(wiw_dashboard.settings, 'WIW_PASSWORD', 'test-password', raising=False)
    monkeypatch.setattr(wiw_dashboard, '_live_wiw_snapshot', lambda now: {
        'open_shifts_available': 17,
        'source': 'wiw-live-readonly',
        'live_error': '',
    })

    response = auth_admin.get('/api/admin/mobile-dashboard/')

    assert response.status_code == 200
    assert response.data['open_shifts_available'] == 18
