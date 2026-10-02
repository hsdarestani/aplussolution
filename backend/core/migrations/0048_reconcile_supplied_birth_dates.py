from difflib import SequenceMatcher
from importlib import import_module

from django.db import migrations


SOURCE_MARKER = 'manual_birth_date_reconcile_2026_10_02'
REQUIRED_MASTER_FIELDS = (
    'street',
    'postal_code',
    'city',
    'birth_date',
    'nationality',
    'iban',
    'full_address',
)


def normalise(value):
    return (
        ' '.join(str(value or '').strip().split())
        .casefold()
        .replace('ß', 'ss')
        .replace('ä', 'ae')
        .replace('ö', 'oe')
        .replace('ü', 'ue')
    )


def recalculate(master):
    data = dict(master.data or {})
    missing = [field for field in REQUIRED_MASTER_FIELDS if data.get(field) in (None, '', [], {})]
    master.missing_fields = missing
    master.completeness = round(
        100 * (len(REQUIRED_MASTER_FIELDS) - len(missing)) / len(REQUIRED_MASTER_FIELDS)
    )


def load_supplied_birth_dates():
    previous = import_module('core.migrations.0043_seed_employee_birth_dates')
    return {
        normalise(full_name): birth_date
        for full_name, birth_date in previous.BIRTH_DATES.items()
    }


def find_birth_date(worker, lookup):
    first = normalise(worker.user.first_name)
    last = normalise(worker.user.last_name)
    full = normalise(f'{worker.user.first_name} {worker.user.last_name}')

    if full in lookup:
        return lookup[full]

    if not first or not last:
        return None

    first_token = first.split()[0]
    for supplied_full, birth_date in lookup.items():
        # Exact surname plus tolerant given-name handling. This covers records
        # where the app stores only the first given name while the supplied
        # list contains additional given names.
        if not supplied_full.endswith(' ' + last):
            continue
        supplied_given = supplied_full[: -(len(last) + 1)].strip()
        if not supplied_given:
            continue
        supplied_first_token = supplied_given.split()[0]

        if (
            supplied_given == first
            or supplied_given.startswith(first + ' ')
            or first.startswith(supplied_given + ' ')
            or supplied_first_token == first_token
            or SequenceMatcher(None, supplied_first_token, first_token).ratio() >= 0.88
        ):
            return birth_date

    return None


def reconcile_birth_dates(apps, schema_editor):
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    EmployeeMasterData = apps.get_model('core', 'EmployeeMasterData')
    lookup = load_supplied_birth_dates()

    for worker in WorkerProfile.objects.select_related('user').all():
        birth_date = find_birth_date(worker, lookup)
        if not birth_date:
            continue

        master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
        data = dict(master.data or {})
        source_map = dict(master.source_map or {})

        data['birth_date'] = birth_date
        source_map['birth_date'] = SOURCE_MARKER
        master.data = data
        master.source_map = source_map
        recalculate(master)
        master.save(update_fields=['data', 'source_map', 'missing_fields', 'completeness', 'updated_at'])


def reverse_reconcile(apps, schema_editor):
    EmployeeMasterData = apps.get_model('core', 'EmployeeMasterData')
    for master in EmployeeMasterData.objects.all():
        source_map = dict(master.source_map or {})
        if source_map.get('birth_date') != SOURCE_MARKER:
            continue

        data = dict(master.data or {})
        data.pop('birth_date', None)
        source_map.pop('birth_date', None)

        master.data = data
        master.source_map = source_map
        recalculate(master)
        master.save(update_fields=['data', 'source_map', 'missing_fields', 'completeness', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0047_add_qureshi_birth_date'),
    ]

    operations = [
        migrations.RunPython(reconcile_birth_dates, reverse_reconcile),
    ]
