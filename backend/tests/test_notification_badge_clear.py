import pytest
from django.utils import timezone

from core.models import Notification
from core import notification_badge_views


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
