from django.db import migrations


SOURCE_MARKER = 'manual_birth_date_qureshi_2026_10_02'
REQUIRED_MASTER_FIELDS = (
    'street',
    'postal_code',
    'city',
    'birth_date',
    'nationality',
    'iban',
    'full_address',
)

TARGET_NAMES = {
    'muhammad talha qureshi',
    'talha qureshi',
}


def normalise(value):
    value = ' '.join(str(value or '').strip().split()).casefold()
    return value.replace('ß', 'ss')


def recalculate(master):
    data = dict(master.data or {})
    missing = [field for field in REQUIRED_MASTER_FIELDS if data.get(field) in (None, '', [], {})]
    master.missing_fields = missing
    master.completeness = round(
        100 * (len(REQUIRED_MASTER_FIELDS) - len(missing)) / len(REQUIRED_MASTER_FIELDS)
    )


def add_birth_date(apps, schema_editor):
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    EmployeeMasterData = apps.get_model('core', 'EmployeeMasterData')

    for worker in WorkerProfile.objects.select_related('user').all():
        full_name = normalise(f'{worker.user.first_name} {worker.user.last_name}')
        if full_name not in TARGET_NAMES:
            continue

        master, _ = EmployeeMasterData.objects.get_or_create(worker=worker)
        data = dict(master.data or {})
        source_map = dict(master.source_map or {})

        data['birth_date'] = '01.04.2001'
        source_map['birth_date'] = SOURCE_MARKER

        master.data = data
        master.source_map = source_map
        recalculate(master)
        master.save(update_fields=['data', 'source_map', 'missing_fields', 'completeness', 'updated_at'])


def remove_birth_date(apps, schema_editor):
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
        ('core', '0046_auev_batch_exports'),
    ]

    operations = [
        migrations.RunPython(add_birth_date, remove_birth_date),
    ]
