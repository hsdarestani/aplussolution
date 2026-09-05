from django.db import migrations


def align_client_links(apps, schema_editor):
    Shift = apps.get_model('core', 'Shift')
    ClientOrder = apps.get_model('core', 'ClientOrder')

    shift_updates = []
    for shift in Shift.objects.select_related('location').all().iterator():
        location_client_id = getattr(shift.location, 'client_id', None)
        if location_client_id and shift.client_id != location_client_id:
            shift.client_id = location_client_id
            shift_updates.append(shift)
    if shift_updates:
        Shift.objects.bulk_update(shift_updates, ['client'], batch_size=500)

    order_updates = []
    for order in ClientOrder.objects.select_related('location').exclude(location__isnull=True).iterator():
        location_client_id = getattr(order.location, 'client_id', None)
        if location_client_id and order.client_id != location_client_id:
            order.client_id = location_client_id
            order_updates.append(order)
    if order_updates:
        ClientOrder.objects.bulk_update(order_updates, ['client'], batch_size=500)


def noop_reverse(apps, schema_editor):
    # The previous mismatched client ids are not valid business state and cannot
    # be reconstructed safely after canonical directory merges.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0024_shorten_spenerhaus_display_name'),
    ]

    operations = [
        migrations.RunPython(align_client_links, noop_reverse),
    ]
