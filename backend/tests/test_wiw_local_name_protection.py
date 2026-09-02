import pytest
from django.utils import timezone

from core.models import ClientCompany, Location


@pytest.mark.django_db
def test_wiw_refresh_cannot_overwrite_locally_renamed_location():
    client = ClientCompany.objects.create(name='Kunde', customer_number='WIW-1')
    old_sync = timezone.now()
    location = Location.objects.create(
        client=client,
        name='Mein Einsatzort',
        address='Frankfurt',
        wiw_location_id='loc-1',
        wiw_synced_at=old_sync,
    )

    location.name = 'Name aus WIW'
    location.address = 'Neue Adresse'
    location.wiw_synced_at = old_sync + timezone.timedelta(minutes=5)
    location.save()
    location.refresh_from_db()

    assert location.name == 'Mein Einsatzort'
    assert location.address == 'Neue Adresse'
