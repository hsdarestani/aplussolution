from django.db import migrations


LONG_NAME = 'VCH- Hotel Phillipp-Jakob-Spenerhaus'
SHORT_NAME = 'Hotel Spenerhaus'


def shorten_spenerhaus_name(apps, schema_editor):
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Location = apps.get_model('core', 'Location')

    # Display-only cleanup. Keep customer_number and every WIW external id/payload
    # untouched so existing and future When I Work synchronization keeps resolving
    # to the same A+ records.
    ClientCompany.objects.filter(name__iexact=LONG_NAME).update(name=SHORT_NAME)
    Location.objects.filter(name__iexact=LONG_NAME).update(name=SHORT_NAME)


def noop_reverse(apps, schema_editor):
    # Do not restore the verbose WIW label on rollback; the short label is locally
    # managed business display data.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0023_deactivate_legacy_wiw_positions'),
    ]

    operations = [
        migrations.RunPython(shorten_spenerhaus_name, noop_reverse),
    ]
