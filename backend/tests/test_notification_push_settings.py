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


@pytest.mark.django_db
def test_settings_show_actual_copy_without_freezing_dynamic_templates(worker_user):
    from core.notification_settings import all_push_rule_payloads
    first = Notification.objects.create(user=worker_user, kind='open-shift-created-preview',
                                        title='Neue Schicht verfügbar', body='03.09.2026 · Frankfurt')
    rules = all_push_rule_payloads()
    rule = next(row for row in rules if row['key'] == 'open_shift')
    assert rule['display_title'] == first.title
    assert rule['display_body'] == first.body
    assert rule['preview_source'] == 'latest'
    save_push_rules(rules)
    next_notification = Notification(user=worker_user, kind='open-shift-created-next',
                                     title='Neue Schicht verfügbar', body='04.09.2026 · Wiesbaden')
    assert render_push_notification(next_notification)[2] == next_notification.body
    rule['title_template'] = 'Neue Einsatzmöglichkeit'
    save_push_rules([rule])
    assert render_push_notification(next_notification)[1] == 'Neue Einsatzmöglichkeit'


@pytest.mark.django_db
def test_unsent_notification_families_have_readable_examples():
    from core.notification_settings import all_push_rule_payloads
    for rule in all_push_rule_payloads():
        assert rule['display_title'] and rule['display_title'] != '{title}'
        assert rule['display_body'] != '{body}'
        assert rule['preview_source'] == 'example'
