import re
import unicodedata

from django.db import migrations


def _normalize(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace('ß', 'ss').casefold()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def _unique_number(ClientCompany, base):
    candidate = base[:50]
    index = 1
    while ClientCompany.objects.filter(customer_number=candidate).exists():
        index += 1
        suffix = f'-{index}'
        candidate = f'{base[:50-len(suffix)]}{suffix}'
    return candidate


def restore_customer_directory(apps, schema_editor):
    ClientCompany = apps.get_model('core', 'ClientCompany')
    Location = apps.get_model('core', 'Location')

    # A+ is the source of truth now. Keep the business-edited display name
    # "Marthas" instead of allowing old WIW-era canonicalization to restore
    # "Martha" during a deployment.
    martha_aliases = {
        'martha',
        'marthas',
        'martha s',
        'marthas finest',
        'martha s finest',
    }
    martha_candidates = [
        client for client in ClientCompany.objects.all()
        if _normalize(client.name) in martha_aliases
    ]
    if martha_candidates:
        martha_candidates.sort(
            key=lambda client: (
                0 if _normalize(client.name) == 'marthas' else 1,
                0 if client.active else 1,
                str(getattr(client, 'created_at', '') or ''),
            )
        )
        marthas = martha_candidates[0]
        changed = []
        if marthas.name != 'Marthas':
            marthas.name = 'Marthas'
            changed.append('name')
        if not marthas.active:
            marthas.active = True
            changed.append('active')
        if changed:
            marthas.save(update_fields=changed)

    # Stadthaus must be present in the customer picker. Re-activate an existing
    # row if one exists; otherwise create the local A+ customer and its default
    # location so shift creation works immediately.
    stadthaus_aliases = {
        'stadthaus am markt',
        'stadthaus markt',
        'stadhaust am markt',
    }
    stadthaus_candidates = [
        client for client in ClientCompany.objects.all()
        if _normalize(client.name) in stadthaus_aliases
    ]
    if stadthaus_candidates:
        stadthaus_candidates.sort(
            key=lambda client: (
                0 if _normalize(client.name) == 'stadthaus am markt' else 1,
                0 if client.active else 1,
                str(getattr(client, 'created_at', '') or ''),
            )
        )
        stadthaus = stadthaus_candidates[0]
        changed = []
        if stadthaus.name != 'Stadthaus am Markt':
            stadthaus.name = 'Stadthaus am Markt'
            changed.append('name')
        if not stadthaus.active:
            stadthaus.active = True
            changed.append('active')
        if changed:
            stadthaus.save(update_fields=changed)
    else:
        stadthaus = ClientCompany.objects.create(
            name='Stadthaus am Markt',
            customer_number=_unique_number(ClientCompany, 'APLUS-STADTHAUS-AM-MARKT'),
            active=True,
        )

    if not Location.objects.filter(client=stadthaus, active=True).exists():
        Location.objects.create(
            client=stadthaus,
            name='Stadthaus am Markt',
            address=stadthaus.address or 'Stadthaus am Markt',
            active=True,
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0031_merge_musa_jamali_duplicate_worker'),
    ]

    operations = [
        migrations.RunPython(restore_customer_directory, noop_reverse),
    ]
