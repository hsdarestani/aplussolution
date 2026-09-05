from django.db import migrations


INACTIVE_POSITION_NAMES = (
    'Garderobe',
    'Koch',
    'Promotion',
    'Host',
    'Bar-Support',
    'Serviceleitung',
)


def restore_inactive_positions(apps, schema_editor):
    Position = apps.get_model('core', 'Position')
    Position.objects.filter(name__in=INACTIVE_POSITION_NAMES).update(active=False)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0025_align_shift_clients_with_locations'),
    ]

    operations = [
        migrations.RunPython(restore_inactive_positions, noop_reverse),
    ]
