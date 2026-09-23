import pytest

from core.models import Notification
from core import push_notifications, push_signals


@pytest.mark.django_db(transaction=True)
def test_open_shift_push_is_debounced_for_aggregation(monkeypatch, worker_user):
    aggregate_calls = []
    immediate_calls = []

    monkeypatch.setattr(push_signals, 'push_provider_configured', lambda: True)
    monkeypatch.setattr(
        push_signals.send_coalesced_notification_push,
        'apply_async',
        lambda *, args, countdown: aggregate_calls.append((args, countdown)),
    )
    monkeypatch.setattr(
        push_signals.send_notification_push,
        'delay',
        lambda notification_id: immediate_calls.append(notification_id),
    )

    notification = Notification.objects.create(
        user=worker_user,
        kind='open-shift-batch-test-1',
        title='Neue OpenShift verfügbar',
        body='Test',
        action_url='/schedule',
    )

    assert immediate_calls == []
    assert aggregate_calls == [
        ([str(notification.id)], push_notifications.PUSH_AGGREGATION_WINDOW_SECONDS)
    ]


@pytest.mark.django_db
def test_burst_push_uses_one_counted_notification(monkeypatch, worker_user):
    rows = [
        Notification.objects.create(
            user=worker_user,
            kind=f'open-shift-batch-test-{index}',
            title='Neue OpenShift verfügbar',
            body=f'Schicht {index}',
            action_url='/schedule',
        )
        for index in range(1, 4)
    ]

    deliveries = []

    def fake_delivery(notification, **kwargs):
        deliveries.append((notification.id, kwargs))
        return {'sent': 1, 'failed': 0, 'deactivated': 0, 'skipped': 0}

    monkeypatch.setattr(push_notifications, 'deliver_notification', fake_delivery)

    early = push_notifications.send_coalesced_notification_push(str(rows[0].id))
    assert early == {'coalesced': 1, 'sent': 0}
    assert deliveries == []

    latest = push_notifications.send_coalesced_notification_push(str(rows[-1].id))
    assert latest['sent'] == 1
    assert latest['coalesced'] == 3
    assert len(deliveries) == 1
    sent_id, overrides = deliveries[0]
    assert sent_id == rows[-1].id
    assert overrides['title_override'] == '3 neue OpenShifts verfügbar'
    assert overrides['body_override'] == '3 neue Schichten wurden veröffentlicht. Für Details bitte die App öffnen.'


@pytest.mark.django_db
def test_non_batch_message_still_sends_immediately(monkeypatch, worker_user):
    deliveries = []

    notification = Notification.objects.create(
        user=worker_user,
        kind='message-direct-test',
        title='Neue Nachricht',
        body='Hallo',
        action_url='/messages',
    )
    monkeypatch.setattr(
        push_notifications,
        'deliver_notification',
        lambda item, **kwargs: deliveries.append((item.id, kwargs)) or {
            'sent': 1, 'failed': 0, 'deactivated': 0, 'skipped': 0
        },
    )

    result = push_notifications.send_coalesced_notification_push(str(notification.id))

    assert result['sent'] == 1
    assert deliveries == [(notification.id, {})]
