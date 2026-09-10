import pytest

from core.models import Notification
from core.push_models import PushDelivery, PushDevice
from core import push_notifications


@pytest.mark.django_db
def test_same_notification_is_sent_only_once_per_device(monkeypatch, worker_user):
    device = PushDevice.objects.create(
        user=worker_user,
        platform=PushDevice.Platform.ANDROID,
        token='idempotent-' + ('a' * 64),
    )
    notification = Notification.objects.create(
        user=worker_user,
        kind='portal-registration-complete-test',
        title='Mitarbeiter registriert',
        body='Test hat die Registrierung abgeschlossen.',
    )
    sends = []
    monkeypatch.setattr(push_notifications, 'push_provider_status', lambda: {'android': True, 'ios': False})
    monkeypatch.setattr(
        push_notifications,
        '_send_android',
        lambda *_: (sends.append('sent') is None and True, '', False),
    )

    first = push_notifications.deliver_notification(notification)
    second = push_notifications.deliver_notification(notification)

    assert first == {'sent': 1, 'failed': 0, 'deactivated': 0, 'skipped': 0}
    assert second == {'sent': 0, 'failed': 0, 'deactivated': 0, 'skipped': 1}
    assert sends == ['sent']
    delivery = PushDelivery.objects.get(notification=notification, device=device)
    assert delivery.sent_at is not None


@pytest.mark.django_db
def test_failed_delivery_releases_claim_for_retry(monkeypatch, worker_user):
    device = PushDevice.objects.create(
        user=worker_user,
        platform=PushDevice.Platform.ANDROID,
        token='retryable-' + ('b' * 64),
    )
    notification = Notification.objects.create(
        user=worker_user,
        title='Neue Schicht',
        body='Bitte prüfen.',
    )
    attempts = []

    def send(*_):
        attempts.append(1)
        if len(attempts) == 1:
            return False, 'FCM transport: temporary failure', False
        return True, '', False

    monkeypatch.setattr(push_notifications, 'push_provider_status', lambda: {'android': True, 'ios': False})
    monkeypatch.setattr(push_notifications, '_send_android', send)

    first = push_notifications.deliver_notification(notification)
    assert first['failed'] == 1
    assert not PushDelivery.objects.filter(notification=notification, device=device).exists()

    second = push_notifications.deliver_notification(notification)
    assert second['sent'] == 1
    assert len(attempts) == 2
    assert PushDelivery.objects.get(notification=notification, device=device).sent_at is not None
