from django.db import migrations


INACTIVE_POSITION_NAMES = (
    'Garderobe',
    'Koch',
    'Promotion',
    'Host',
    'Bar-Support',
    'Serviceleitung',
)


def deactivate_positions(apps, schema_editor):
    Position = apps.get_model('core', 'Position')
    Position.objects.filter(name__in=INACTIVE_POSITION_NAMES).update(active=False)


def noop_reverse(apps, schema_editor):
    # Do not reactivate positions on rollback: their active state is locally
    # managed business data, not a safe schema default.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0022_reconcile_izabella_housekeeping_september'),
    ]

    operations = [
        migrations.RunPython(deactivate_positions, noop_reverse),
    ]
