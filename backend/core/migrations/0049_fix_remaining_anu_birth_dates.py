from django.db import migrations


SOURCE_MARKER = 'manual_birth_date_fix_2026_10_02'
REQUIRED_MASTER_FIELDS = (
    'street',
    'postal_code',
    'city',
    'birth_date',
    'nationality',
    'iban',
    'full_address',
)

BIRTH_DATES = {
    'shahrzad bagheri': '04.03.2000',
    'shahrzad bagher': '04.03.2000',
    'fatemehr bagheri hosseinabadi': '04.03.2000',
    'fatemeh bagheri hosseinabadi': '04.03.2000',
    'yohannes kifle': '10.08.1991',
}


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


def apply_birth_dates(apps, schema_editor):
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    EmployeeMasterData = apps.get_model('core', 'EmployeeMasterData')

    for worker in WorkerProfile.objects.select_related('user').all():
        candidates = {
            normalise(f'{worker.user.first_name} {worker.user.last_name}'),
            normalise(f'{worker.user.last_name} {worker.user.first_name}'),
        }
        birth_date = next((BIRTH_DATES[name] for name in candidates if name in BIRTH_DATES), None)
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


def reverse_birth_dates(apps, schema_editor):
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
        ('core', '0048_reconcile_supplied_birth_dates'),
    ]

    operations = [
        migrations.RunPython(apply_birth_dates, reverse_birth_dates),
    ]
