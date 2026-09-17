from django.db import migrations
from django.db.models import Q


HOTEL_NAME = 'Hotel Spenerhaus'
HOTEL_ADDRESS = 'Dominikanergasse 5, 60311 Frankfurt am Main, Deutschland'


def _location_rank(location, hotel_id):
    name = str(location.name or '').strip().casefold()
    address = str(location.address or '').strip().casefold()
    has_address = 'dominikanergasse 5' in address
    exact_name = name == HOTEL_NAME.casefold()
    return (
        0 if exact_name and has_address else 1,
        0 if has_address else 1,
        0 if exact_name else 1,
        0 if location.client_id == hotel_id else 1,
        0 if location.active else 1,
        str(getattr(location, 'created_at', '') or ''),
    )


def cleanup_spenerhaus_directory(apps, schema_editor):
    ClientCompany = apps.get_model('core', 'ClientCompany')
    ClientOrder = apps.get_model('core', 'ClientOrder')
    Location = apps.get_model('core', 'Location')
    Position = apps.get_model('core', 'Position')
    Shift = apps.get_model('core', 'Shift')

    # Front Office was accidentally treated as bootstrap master data. Keep the
    # row for historical FK integrity, but hide it from active position pickers.
    # No shift is deleted or rewritten because of this cleanup.
    Position.objects.filter(
        Q(name__iexact='Front Office') |
        Q(name__iexact='Front-Office') |
        Q(name__iexact='Front - Office')
    ).update(active=False)

    # Repair the hotel directory in-place. We preserve every existing shift and
    # only repoint its client/location foreign keys to the real Spenerhaus site.
    hotel_clients = list(
        ClientCompany.objects.filter(name__icontains='Spenerhaus').order_by('created_at')
    )
    if not hotel_clients:
        return

    hotel_clients.sort(
        key=lambda client: (
            0 if str(client.name or '').strip().casefold() == HOTEL_NAME.casefold() else 1,
            0 if client.active else 1,
            str(getattr(client, 'created_at', '') or ''),
        )
    )
    hotel = hotel_clients[0]
    client_ids = [client.pk for client in hotel_clients]

    client_changes = []
    if hotel.name != HOTEL_NAME:
        hotel.name = HOTEL_NAME
        client_changes.append('name')
    if hotel.address != HOTEL_ADDRESS:
        hotel.address = HOTEL_ADDRESS
        client_changes.append('address')
    if not hotel.active:
        hotel.active = True
        client_changes.append('active')
    if client_changes:
        hotel.save(update_fields=client_changes)

    locations = list(
        Location.objects.filter(client_id__in=client_ids).order_by('created_at')
    )
    if locations:
        locations.sort(key=lambda location: _location_rank(location, hotel.pk))
        canonical_location = locations[0]
        location_changes = []
        if canonical_location.client_id != hotel.pk:
            canonical_location.client_id = hotel.pk
            location_changes.append('client')
        if canonical_location.name != HOTEL_NAME:
            canonical_location.name = HOTEL_NAME
            location_changes.append('name')
        if canonical_location.address != HOTEL_ADDRESS:
            canonical_location.address = HOTEL_ADDRESS
            location_changes.append('address')
        if not canonical_location.active:
            canonical_location.active = True
            location_changes.append('active')
        if location_changes:
            canonical_location.save(update_fields=location_changes)
    else:
        canonical_location = Location.objects.create(
            client_id=hotel.pk,
            name=HOTEL_NAME,
            address=HOTEL_ADDRESS,
            active=True,
        )
        locations = [canonical_location]

    location_ids = [location.pk for location in locations]

    # Include both client-based and location-based matches because earlier WIW
    # cleanup could leave these two foreign keys disagreeing. Bulk update keeps
    # the Shift rows, assignments, slots, notes, status and timestamps intact.
    Shift.objects.filter(
        Q(client_id__in=client_ids) | Q(location_id__in=location_ids)
    ).update(
        client_id=hotel.pk,
        location_id=canonical_location.pk,
    )

    # Keep linked orders consistent with the repaired shifts without deleting or
    # recreating any order/history rows.
    ClientOrder.objects.filter(
        Q(client_id__in=client_ids) | Q(location_id__in=location_ids)
    ).update(
        client_id=hotel.pk,
        location_id=canonical_location.pk,
    )


def noop_reverse(apps, schema_editor):
    # This migration intentionally repairs live business data. Re-enabling the
    # accidental position or restoring mismatched hotel links would be unsafe.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0032_restore_customer_directory'),
    ]

    operations = [
        migrations.RunPython(cleanup_spenerhaus_directory, noop_reverse),
    ]
