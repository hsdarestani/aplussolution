import pytest
from django.utils import timezone

from core.models import Notification
from core.push_models import PushDevice
from core import notification_badge_views, notification_badges


@pytest.mark.django_db
def test_read_all_marks_notifications_read_and_clears_native_badge(monkeypatch, auth_worker, worker_user):
    notification = Notification.objects.create(
        user=worker_user,
        title='Neue Mitteilung',
        body='Bitte prüfen.',
    )
    calls = []
    monkeypatch.setattr(
        notification_badge_views,
        'clear_ios_badge',
        lambda user: calls.append(user.pk) or {'sent': 1, 'failed': 0, 'deactivated': 0, 'skipped': 0},
    )

    response = auth_worker.post('/api/operations/notifications/read-all/', {}, format='json')

    assert response.status_code == 200
    assert response.json()['updated'] == 1
    assert response.json()['badge']['sent'] == 1
    assert calls == [worker_user.pk]
    notification.refresh_from_db()
    assert notification.read_at is not None


@pytest.mark.django_db
def test_read_all_retries_badge_clear_even_when_database_is_already_read(monkeypatch, auth_worker, worker_user):
    Notification.objects.create(
        user=worker_user,
        title='Bereits gelesen',
        body='Alt',
        read_at=timezone.now(),
    )
    calls = []
    monkeypatch.setattr(
        notification_badge_views,
        'clear_ios_badge',
        lambda user: calls.append(user.pk) or {'sent': 1, 'failed': 0, 'deactivated': 0, 'skipped': 0},
    )

    response = auth_worker.post('/api/operations/notifications/read-all/', {}, format='json')

    assert response.status_code == 200
    assert response.json()['updated'] == 0
    assert calls == [worker_user.pk]


@pytest.mark.django_db
def test_ios_badge_clear_sends_explicit_zero_to_apns(monkeypatch, worker_user):
    device = PushDevice.objects.create(
        user=worker_user,
        platform=PushDevice.Platform.IOS,
        token='d' * 64,
    )
    posted = []

    class Response:
        status_code = 200
        text = ''

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def post(self, url, headers=None, json=None):
            posted.append((url, headers, json))
            return Response()

    monkeypatch.setattr(notification_badges, 'push_provider_status', lambda: {'android': False, 'ios': True})
    monkeypatch.setattr(
        notification_badges,
        '_apns_values',
        lambda: ('TEAM', 'KEY', 'PRIVATE', 'de.aplussolution.workforce', False),
    )
    monkeypatch.setattr(notification_badges, '_apns_provider_token', lambda: 'provider-token')
    monkeypatch.setattr(notification_badges.httpx, 'Client', lambda **_kwargs: Client())

    result = notification_badges.clear_ios_badge(worker_user)

    assert result['sent'] == 1
    assert posted == [(
        f'https://api.push.apple.com/3/device/{device.token}',
        {
            'authorization': 'bearer provider-token',
            'apns-topic': 'de.aplussolution.workforce',
            'apns-push-type': 'alert',
            'apns-priority': '10',
        },
        {'aps': {'badge': 0}},
    )]
