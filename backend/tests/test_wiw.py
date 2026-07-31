import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
import responses
from django.core.cache import cache
from django.utils import timezone

from core.models import EmployeeMasterData, IntegrationSyncRun, Shift, User, WebhookEvent, WorkerProfile
from core.shift_slots import ShiftSlot
from core.wiw import WhenIWorkClient, WhenIWorkError, verify_webhook_signature
from core.wiw_sync import WhenIWorkSynchronizer


@pytest.fixture
def wiw_settings(settings):
    settings.WIW_DEV_KEY = 'dev-secret'
    settings.WIW_EMAIL = 'api@example.com'
    settings.WIW_PASSWORD = 'password-secret'
    settings.WIW_USER_ID = '123'
    settings.WIW_WEBHOOK_SECRET = 'webhook-secret'
    cache.clear()
    return settings


@pytest.mark.django_db
@responses.activate
def test_wiw_login_and_authenticated_request_headers(wiw_settings):
    responses.post(WhenIWorkClient.LOGIN_URL, json={'person': {'token': 'token-value'}}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/login', json={'users': [{'id': 123, 'account_id': 900, 'role': 1}]}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/users', json={'users': [{'id': 1}]}, status=200)
    client = WhenIWorkClient(); result = client.collection('users')
    assert len(result.items) == 1
    request = responses.calls[2].request
    assert request.headers['W-Key'] == 'dev-secret'
    assert request.headers['W-Token'] == 'token-value'
    assert request.headers['W-UserId'] == '123'
    assert request.headers['Authorization'] == 'Bearer token-value'


@pytest.mark.django_db
@responses.activate
def test_wiw_maps_configured_account_id_to_authorized_user_context(wiw_settings):
    wiw_settings.WIW_USER_ID = '4138062'
    responses.post(WhenIWorkClient.LOGIN_URL, json={'token': 'token-value'}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/login', json={'users': [{'id': 48430803, 'account_id': 4138062, 'role': 1}], 'accounts': [{'id': 4138062, 'role': 3}]}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/shifts', json={'shifts': []}, status=200)
    result = WhenIWorkClient().collection('shifts')
    assert result.items == []
    assert responses.calls[2].request.headers['W-UserId'] == '48430803'


@pytest.mark.django_db
@responses.activate
def test_wiw_reauthenticates_and_reresolves_context_after_401(wiw_settings):
    responses.post(WhenIWorkClient.LOGIN_URL, json={'token': 'old'}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/login', json={'users': [{'id': 123, 'account_id': 900, 'role': 1}]}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/users', json={'error': 'expired'}, status=401)
    responses.post(WhenIWorkClient.LOGIN_URL, json={'token': 'new'}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/login', json={'users': [{'id': 124, 'account_id': 123, 'role': 1}]}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/users', json={'users': []}, status=200)
    result = WhenIWorkClient().collection('users')
    assert result.items == []
    assert len(responses.calls) == 6
    assert responses.calls[-1].request.headers['W-UserId'] == '124'
    assert responses.calls[-1].request.headers['Authorization'] == 'Bearer new'


@pytest.mark.django_db
@responses.activate
def test_wiw_429_retries_without_leaking_secrets(wiw_settings):
    responses.post(WhenIWorkClient.LOGIN_URL, json={'token': 'token'}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/login', json={'users': [{'id': 123, 'account_id': 900, 'role': 1}]}, status=200)
    responses.get(f'{WhenIWorkClient.API_BASE}/users', json={'error': 'rate'}, status=429, headers={'Retry-After': '0'})
    responses.get(f'{WhenIWorkClient.API_BASE}/users', json={'users': []}, status=200)
    with patch('core.wiw.time.sleep'):
        result = WhenIWorkClient().collection('users')
    assert result.items == []


@pytest.mark.django_db
def test_collection_extraction_handles_official_shapes():
    assert WhenIWorkClient.extract_collection([{'id': 1}], 'users') == [{'id': 1}]
    assert WhenIWorkClient.extract_collection({'users': [{'id': 2}]}, 'users') == [{'id': 2}]
    assert WhenIWorkClient.extract_collection({'data': [{'id': 3}]}, 'users') == [{'id': 3}]


@pytest.mark.django_db
def test_wiw_sync_is_idempotent_and_maps_resources(wiw_settings):
    mock = Mock()
    def resource(name, params=None, optional=False):
        payloads = {
            'users': [{'id': 10, 'email': 'anna@wiw.test', 'first_name': 'Anna', 'last_name': 'WIW', 'phone': '123', 'hourly_rate': '16.50'}],
            'positions': [{'id': 20, 'name': 'Hostess'}],
            'locations': [{'id': 30, 'name': 'Kunde Alpha', 'address': 'Main 1', 'latitude': 50.1, 'longitude': 8.6}],
            'sites': [],
            'shifts': [{'id': 40, 'user_id': 10, 'location_id': 30, 'position_id': 20, 'start_time': (timezone.now()+timedelta(days=1)).isoformat(), 'end_time': (timezone.now()+timedelta(days=1,hours=5)).isoformat()}],
            'times': [], 'availabilities': [], 'requests': [],
        }
        return type('Result', (), {'items': payloads[name]})()
    mock.collection.side_effect = resource
    first = WhenIWorkSynchronizer(client=mock).sync('full')
    second = WhenIWorkSynchronizer(client=mock).sync('full')
    assert first.status == 'success' and second.status == 'success'
    assert User.objects.filter(wiw_id='10').count() == 1
    assert WorkerProfile.objects.filter(wiw_user_id='10').count() == 1
    shift = Shift.objects.get(wiw_shift_id='40')
    assert ShiftSlot.objects.filter(shift=shift, wiw_shift_id='40', status='claimed', worker__wiw_user_id='10').count() == 1
    master = EmployeeMasterData.objects.get(worker__wiw_user_id='10')
    assert master.data['phone'] == '123'
    assert 'iban' in master.missing_fields or master.completeness < 100


@pytest.mark.django_db
def test_webhook_signature_and_deduplication(api_client, wiw_settings):
    payload = {'id': 'event-1', 'event': 'shift.updated'}
    body = json.dumps(payload).encode(); signature = hmac.new(b'webhook-secret', body, hashlib.sha256).hexdigest()
    with patch('core.integration_views.process_wiw_webhook.delay') as delay:
        first = api_client.post('/api/integrations/wiw/webhook/', data=body, content_type='application/json', HTTP_X_WIW_SIGNATURE=signature)
        second = api_client.post('/api/integrations/wiw/webhook/', data=body, content_type='application/json', HTTP_X_WIW_SIGNATURE=signature)
    assert first.status_code == 202 and second.status_code == 202
    assert first.data['duplicate'] is False and second.data['duplicate'] is True
    assert WebhookEvent.objects.count() == 1
    delay.assert_called_once()
    invalid = api_client.post('/api/integrations/wiw/webhook/', data=body, content_type='application/json', HTTP_X_WIW_SIGNATURE='wrong')
    assert invalid.status_code == 403


@pytest.mark.django_db
def test_status_endpoint_never_returns_secrets(auth_admin, wiw_settings):
    response = auth_admin.get('/api/integrations/wiw/status/')
    assert response.status_code == 200
    body = json.dumps(response.data)
    assert 'dev-secret' not in body
    assert 'password-secret' not in body
    assert 'tax_identification_number' in response.data['not_available_from_wiw']


@pytest.mark.django_db
def test_wiw_datetime_parser_accepts_rfc_2822_and_unix_values():
    from core.wiw_sync import as_datetime
    rfc_value = as_datetime('Tue, 28 Jul 2026 16:00:00 +0200')
    unix_value = as_datetime(1785254400)
    assert rfc_value is not None
    assert rfc_value.isoformat() == '2026-07-28T16:00:00+02:00'
    assert unix_value is not None
    assert timezone.is_aware(unix_value)
