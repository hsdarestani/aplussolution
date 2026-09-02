from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from core.models import Notification, Position, Shift
from core.operational_notifications import notify_open_shift_available
from core.shift_slots import ShiftSlot


@pytest.fixture
def push_position(db):
    return Position.objects.create(name='Push Wiring Regression Position')


def _future_shift(company, location, push_position, status=Shift.Status.DRAFT):
    start = timezone.now() + timedelta(days=2)
    return Shift.objects.create(
        client=company,
        location=location,
        position=push_position,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        status=status,
        required_count=1,
    )


@pytest.mark.django_db
def test_direct_publish_notifies_open_shift_workers(auth_admin, company, location, push_position):
    shift = _future_shift(company, location, push_position)
    with patch('core.shift_views.notify_open_shift_available') as notify:
        response = auth_admin.post(f'/api/shifts/{shift.id}/publish/', {}, format='json')
    assert response.status_code == 200
    notify.assert_called_once()
    assert notify.call_args.args[0].id == shift.id
    assert notify.call_args.args[1] == 'publish'


@pytest.mark.django_db
def test_create_published_shift_notifies_open_shift_workers(auth_admin, company, location, push_position):
    start = timezone.now() + timedelta(days=3)
    payload = {
        'client': str(company.id),
        'location': str(location.id),
        'position': str(push_position.id),
        'starts_at': start.isoformat(),
        'ends_at': (start + timedelta(hours=5)).isoformat(),
        'status': Shift.Status.PUBLISHED,
        'required_count': 1,
    }
    with patch('core.shift_views.notify_open_shift_available') as notify:
        response = auth_admin.post('/api/shifts/', payload, format='json')
    assert response.status_code == 201, response.data
    notify.assert_called_once()
    assert notify.call_args.args[1] == 'created'


@pytest.mark.django_db
def test_bulk_publish_notifies_open_capacity(auth_admin, company, location, push_position):
    shift = _future_shift(company, location, push_position)
    with patch('core.native_operations.notify_open_shift_available') as notify:
        response = auth_admin.post(
            '/api/operations/bulk-publish/',
            {'ids': [str(shift.id)]},
            format='json',
        )
    assert response.status_code == 200, response.data
    notify.assert_called_once()
    assert notify.call_args.args[0].id == shift.id
    assert notify.call_args.args[1] == 'bulk-publish'


@pytest.mark.django_db
def test_open_shift_fanout_creates_one_admin_summary(admin_user, worker_user, second_worker, company, location, push_position, monkeypatch):
    shift = _future_shift(company, location, push_position, status=Shift.Status.PUBLISHED)
    ShiftSlot.objects.create(shift=shift)
    monkeypatch.setattr('core.operational_notifications.shift_visible_to_worker', lambda *_: True)

    created = notify_open_shift_available(shift, 'regression')

    worker_notifications = Notification.objects.filter(user__role='worker', kind__startswith='open-shift-')
    assert created == worker_notifications.count()
    assert created >= 2
    summaries = Notification.objects.filter(user=admin_user, kind__startswith='admin-open-shift-summary-')
    assert summaries.count() == 1
    assert f'{created} Mitarbeiter' in summaries.get().body
    assert not Notification.objects.filter(user=admin_user, kind__startswith='admin-worker-copy-').exists()


@pytest.mark.django_db
def test_open_shift_zero_worker_fanout_still_confirms_to_admin(admin_user, worker_user, company, location, push_position, monkeypatch):
    shift = _future_shift(company, location, push_position, status=Shift.Status.PUBLISHED)
    ShiftSlot.objects.create(shift=shift)
    monkeypatch.setattr('core.operational_notifications.shift_visible_to_worker', lambda *_: False)

    created = notify_open_shift_available(shift, 'copied-regression')

    assert created == 0
    summary = Notification.objects.get(
        user=admin_user,
        kind__startswith='admin-open-shift-summary-copied-regression-',
    )
    assert summary.title == 'OpenShift veröffentlicht'
    assert 'Keine passenden Mitarbeiter benachrichtigt' in summary.body
