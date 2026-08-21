from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import ClientOrder, Shift


pytestmark = pytest.mark.django_db


def make_order(company, location, client_user):
    start = timezone.now() + timedelta(days=2)
    return ClientOrder.objects.create(
        client=company,
        title='QA Client Order',
        description='2 Servicekräfte für Abendveranstaltung',
        location=location,
        starts_at=start,
        ends_at=start + timedelta(hours=5),
        requested_staff=2,
        status=ClientOrder.Status.NEW,
        created_by=client_user,
    )


def test_admin_confirm_creates_multislot_open_shift_once(auth_admin, company, location, position, client_user):
    order = make_order(company, location, client_user)

    first = auth_admin.patch(f'/api/orders/{order.id}/', {'status': 'confirmed'}, format='json')
    assert first.status_code == 200, first.data

    order.refresh_from_db()
    assert order.status == ClientOrder.Status.CONFIRMED
    assert order.shifts.count() == 1

    shift = order.shifts.get()
    assert shift.client_id == company.id
    assert shift.location_id == location.id
    assert shift.position_id == position.id
    assert shift.starts_at == order.starts_at
    assert shift.ends_at == order.ends_at
    assert shift.required_count == 2
    assert shift.is_open is True
    assert shift.status == Shift.Status.PUBLISHED
    assert shift.slots.exclude(status='cancelled').count() == 2
    assert first.data['planning']['created'] is True

    second = auth_admin.patch(f'/api/orders/{order.id}/', {'status': 'confirmed'}, format='json')
    assert second.status_code == 200, second.data
    assert order.shifts.count() == 1
    assert second.data['planning']['created'] is False


def test_client_cannot_self_confirm_order(auth_client, company, location, position, client_user):
    order = make_order(company, location, client_user)

    response = auth_client.patch(f'/api/orders/{order.id}/', {'status': 'confirmed'}, format='json')

    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == ClientOrder.Status.NEW
    assert order.shifts.count() == 0
