from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import ClientCompany, ClientOrder, Location, Position, Shift


@pytest.mark.django_db
def test_location_reassignment_repairs_existing_shift_and_order_client_links():
    old_client = ClientCompany.objects.create(
        name='WIW Evangelische Akademie',
        customer_number='WIW-EVANGELISCHE',
        active=False,
    )
    martha = ClientCompany.objects.create(
        name='Martha',
        customer_number='APLUS-MARTHA',
        active=True,
    )
    location = Location.objects.create(
        client=old_client,
        name='Evangelische Akademie',
        address='Frankfurt',
        active=True,
        wiw_location_id='91',
    )
    position = Position.objects.create(name='Signal Test Service', active=True)
    starts_at = timezone.now()
    order = ClientOrder.objects.create(
        client=old_client,
        location=location,
        title='Testauftrag',
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=8),
    )
    shift = Shift.objects.create(
        client=old_client,
        location=location,
        position=position,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=8),
    )

    location.client = martha
    location.save(update_fields=['client', 'updated_at'])

    shift.refresh_from_db()
    order.refresh_from_db()
    assert shift.client_id == martha.id
    assert order.client_id == martha.id
    assert shift.location_id == location.id
    assert order.location_id == location.id
