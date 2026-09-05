from unittest.mock import Mock

import pytest

from core.models import ClientCompany, Location
from core.wiw_directory import (
    ACTIVE_CLIENT_NAMES,
    MARTHA_LOCATION_NAMES,
    canonical_client_name,
    canonical_martha_location_name,
    location_aliases,
    normalize_wiw_directory,
)
from core.wiw_schedule_sync import WhenIWorkSynchronizer


@pytest.mark.django_db
def test_wiw_alias_names_resolve_to_business_canonical_names():
    assert canonical_client_name('(2) Marthas') == 'Martha'
    assert canonical_client_name('Marthas Finest') == 'Martha'
    assert canonical_client_name('OMNIA') == 'OMMIA'
    assert canonical_client_name('Manuel Höfel Catering') == 'Höfel Catering'
    assert canonical_martha_location_name('(1) Evangelische Akademie') == 'Evangelische Akademie'
    assert canonical_martha_location_name('Dominikanerkloster') == 'Dominikankloster'


@pytest.mark.django_db
def test_directory_cleanup_merges_duplicates_and_keeps_only_requested_active_structure():
    martha = ClientCompany.objects.create(
        name='Martha', customer_number='M-LOCAL', active=True
    )
    duplicate_martha = ClientCompany.objects.create(
        name='(2) Marthas', customer_number='WIW-200', active=True
    )
    unknown = ClientCompany.objects.create(
        name='Old Customer', customer_number='OLD-1', active=True
    )

    evangelische = Location.objects.create(
        client=martha,
        name='Evangelische Akademie',
        address='Frankfurt',
        active=True,
    )
    duplicate_evangelische = Location.objects.create(
        client=duplicate_martha,
        name='(1) Evangelische Akademie',
        address='Frankfurt',
        wiw_location_id='91',
        active=True,
    )
    Location.objects.create(
        client=duplicate_martha,
        name='Goethe Uni 1',
        address='Frankfurt',
        wiw_site_id='301',
        active=True,
    )
    Location.objects.create(
        client=duplicate_martha,
        name='Dominikankloster',
        address='Frankfurt',
        wiw_site_id='302',
        active=True,
    )
    Location.objects.create(
        client=duplicate_martha,
        name='Martha Root',
        address='Frankfurt',
        wiw_location_id='200',
        active=True,
    )
    Location.objects.create(
        client=unknown,
        name='Old Location',
        address='Frankfurt',
        active=True,
    )

    normalize_wiw_directory()

    active_clients = set(ClientCompany.objects.filter(active=True).values_list('name', flat=True))
    assert active_clients == set(ACTIVE_CLIENT_NAMES)

    martha = ClientCompany.objects.get(name='Martha', active=True)
    active_martha_locations = set(
        Location.objects.filter(client=martha, active=True).values_list('name', flat=True)
    )
    assert active_martha_locations == set(MARTHA_LOCATION_NAMES)

    evangelische.refresh_from_db()
    duplicate_evangelische.refresh_from_db()
    assert duplicate_evangelische.active is False
    assert duplicate_evangelische.wiw_location_id is None
    assert '91' in location_aliases(evangelische, 'location')

    duplicate_martha.refresh_from_db()
    unknown.refresh_from_db()
    assert duplicate_martha.active is False
    assert unknown.active is False

    for client_name in set(ACTIVE_CLIENT_NAMES) - {'Martha'}:
        client = ClientCompany.objects.get(name=client_name, active=True)
        assert Location.objects.filter(client=client, active=True).count() == 1


@pytest.mark.django_db
def test_operational_sync_reuses_canonical_martha_location_without_restoring_wiw_name():
    martha = ClientCompany.objects.create(
        name='Martha', customer_number='M-LOCAL', active=True
    )
    evangelische = Location.objects.create(
        client=martha,
        name='Evangelische Akademie',
        address='Frankfurt',
        wiw_location_id='91',
        active=True,
    )

    client = Mock()
    synchronizer = WhenIWorkSynchronizer(client=client)
    synchronizer.sync_locations([
        {
            'id': 91,
            'name': '(1) Evangelische Akademie',
            'company_name': 'Marthas Finest',
            'address': 'Neue WIW Adresse',
            'active': True,
        }
    ])

    evangelische.refresh_from_db()
    assert evangelische.name == 'Evangelische Akademie'
    assert evangelische.client_id == martha.id
    assert Location.objects.filter(wiw_location_id='91').count() == 1
    assert ClientCompany.objects.filter(active=True, name='Martha').count() == 1
