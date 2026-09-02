import pytest

from core.models import Notification
from core.notification_settings import notification_rule_key, render_push_notification, save_push_rules


@pytest.mark.django_db
def test_push_rule_can_disable_and_override_copy(worker_user):
    notification = Notification.objects.create(
        user=worker_user,
        kind='open-shift-created-test',
        title='Neue Schicht verfügbar',
        body='03.09.2026 10:00 · Testkunde',
    )

    save_push_rules([{
        'key': 'open_shift',
        'enabled': False,
        'title_template': 'NEU: {title}',
        'body_template': '{body}',
    }])

    enabled, title, body, key = render_push_notification(notification)
    assert key == 'open_shift'
    assert enabled is False
    assert title == 'NEU: Neue Schicht verfügbar'
    assert body == '03.09.2026 10:00 · Testkunde'


@pytest.mark.django_db
def test_admin_open_shift_is_its_own_configurable_family(admin_user):
    notification = Notification.objects.create(
        user=admin_user,
        kind='admin-open-shift-summary-created-test',
        title='OpenShift veröffentlicht',
        body='Benachrichtigung für 2 Mitarbeiter ausgelöst',
    )
    assert notification_rule_key(notification) == 'admin_open_shift'
