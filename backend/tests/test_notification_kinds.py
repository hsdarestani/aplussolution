import pytest

from core.models import Notification, User


@pytest.mark.django_db
def test_notification_kind_supports_uuid_scoped_event_names():
    field = Notification._meta.get_field('kind')
    assert field.max_length >= 100

    user = User.objects.create_user(
        'notification-kind@example.com',
        'StrongPass123!',
        role=User.Role.MANAGER,
    )
    kind = 'time-correction-decision-12345678-1234-1234-1234-123456789012'
    notification = Notification.objects.create(
        user=user,
        kind=kind,
        title='Test',
    )
    notification.refresh_from_db()
    assert notification.kind == kind
