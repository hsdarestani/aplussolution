from unittest.mock import Mock

import pytest

from core.models import ClientCompany, Location
from core.wiw_directory import find_location_by_external
from core.wiw_schedule_sync import WhenIWorkSynchronizer


LONG_NAME = 'VCH- Hotel Phillipp-Jakob-Spenerhaus'
SHORT_NAME = 'Hotel Spenerhaus'


@pytest.mark.django_db
def test_spenerhaus_local_name_survives_existing_wiw_location_refresh():
    client = ClientCompany.objects.create(
        name=SHORT_NAME,
        customer_number='APLUS-SPENERHAUS',
        active=True,
    )
    location = Location.objects.create(
        client=client,
        name=SHORT_NAME,
        address='Frankfurt',
        active=True,
        wiw_location_id='55',
    )

    sync = WhenIWorkSynchronizer(client=Mock())
    sync.sync_locations([
        {
            'id': '55',
            'name': LONG_NAME,
            'client_name': LONG_NAME,
            'active': True,
            'address': 'Frankfurt',
        }
    ])

    location.refresh_from_db()
    assert location.name == SHORT_NAME
    assert location.client_id == client.id
    assert location.wiw_location_id == '55'


@pytest.mark.django_db
def test_new_wiw_spenerhaus_id_becomes_alias_of_existing_short_location():
    client = ClientCompany.objects.create(
        name=SHORT_NAME,
        customer_number='APLUS-SPENERHAUS',
        active=True,
    )
    location = Location.objects.create(
        client=client,
        name=SHORT_NAME,
        address='Frankfurt',
        active=True,
        wiw_location_id='55',
    )

    sync = WhenIWorkSynchronizer(client=Mock())
    sync.sync_locations([
        {
            'id': '56',
            'name': LONG_NAME,
            'client_name': LONG_NAME,
            'active': True,
            'address': 'Frankfurt',
        }
    ])

    location.refresh_from_db()
    assert location.name == SHORT_NAME
    assert location.wiw_location_id == '55'
    assert find_location_by_external('location', '56').pk == location.pk
    assert Location.objects.filter(active=True, client=client).count() == 1
