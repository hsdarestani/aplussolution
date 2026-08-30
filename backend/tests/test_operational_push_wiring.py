from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from core.models import Position, Shift


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
