import pytest

from core.models import Notification
from core.push_models import PushDevice
from core import push_notifications, push_signals


@pytest.mark.django_db
def test_register_and_reassign_native_push_device(auth_worker, worker_user, admin_user):
    token = 'a' * 64
    response = auth_worker.post(
        '/api/push/devices/register/',
        {'token': token, 'platform': 'android', 'app_id': 'de.aplussolution.workforce'},
        format='json',
    )
    assert response.status_code == 201
    device = PushDevice.objects.get(token=token)
    assert device.user == worker_user
    assert device.platform == PushDevice.Platform.ANDROID
    assert device.active is True

    auth_worker.force_authenticate(admin_user)
    response = auth_worker.post(
        '/api/push/devices/register/',
        {'token': token, 'platform': 'android', 'app_id': 'de.aplussolution.workforce'},
        format='json',
    )
    assert response.status_code == 200
    device.refresh_from_db()
    assert device.user == admin_user


@pytest.mark.django_db
def test_unregister_native_push_device(auth_worker, worker_user):
    token = 'b' * 64
    PushDevice.objects.create(user=worker_user, platform='ios', token=token)
    response = auth_worker.post('/api/push/devices/unregister/', {'token': token}, format='json')
    assert response.status_code == 200
    assert response.json()['unregistered'] is True
    assert PushDevice.objects.get(token=token).active is False


@pytest.mark.django_db
def test_delivery_uses_registered_device_and_deactivates_invalid_token(monkeypatch, worker_user):
    device = PushDevice.objects.create(user=worker_user, platform='android', token='c' * 64)
    notification = Notification.objects.create(user=worker_user, title='Neue Schicht', body='Bitte prüfen.')

    monkeypatch.setattr(push_notifications, 'push_provider_status', lambda: {'android': True, 'ios': False})
    monkeypatch.setattr(push_notifications, '_send_android', lambda *_: (False, 'FCM 404: UNREGISTERED', True))

    result = push_notifications.deliver_notification(notification)
    device.refresh_from_db()
    assert result == {'sent': 0, 'failed': 1, 'deactivated': 1, 'skipped': 0}
    assert device.active is False
    assert 'UNREGISTERED' in device.last_error


@pytest.mark.django_db(transaction=True)
def test_new_notification_enqueues_native_push_after_commit(monkeypatch, worker_user):
    calls = []
    monkeypatch.setattr(push_signals, 'push_provider_configured', lambda: True)
    monkeypatch.setattr(push_signals.send_notification_push, 'delay', lambda notification_id: calls.append(notification_id))

    Notification.objects.create(user=worker_user, title='Vertrag bereit', action_url='/contracts')
    assert len(calls) == 1


def test_sign_in_with_apple_key_is_not_treated_as_apns_key(monkeypatch):
    monkeypatch.delenv('APNS_KEY_ID', raising=False)
    monkeypatch.delenv('APNS_PRIVATE_KEY', raising=False)
    monkeypatch.setenv('APPLE_TEAM_ID', 'TEAM123')
    monkeypatch.setenv('APPLE_KEY_ID', 'SIGNIN123')
    monkeypatch.setenv('APPLE_PRIVATE_KEY', 'not-an-apns-key')
    assert push_notifications.push_provider_status()['ios'] is False
