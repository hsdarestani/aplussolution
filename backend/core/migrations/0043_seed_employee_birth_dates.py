from django.db import migrations


SOURCE_MARKER = 'manual_birth_date_list_2026_10_01'
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
    'ilayda tarhan': '02.09.1996',
    'michele corrado': '12.04.1963',
    'francesco trulli': '15.11.1992',
    'pinar koca': '31.07.2000',
    'helena hakshia': '24.01.2003',
    'tooba amjad': '11.02.2001',
    'alexandre marques costa': '17.04.1997',
    'saaid aldarwish': '10.01.2001',
    'melis yilmaz': '06.01.2005',
    'wesley maina': '25.01.2003',
    'christian trulli': '19.04.1997',
    'ilhan omerovic': '20.06.2001',
    'delina tewolde': '15.04.2001',
    'christopher skozcny': '27.12.2000',
    'arina martynko': '08.01.2004',
    'ioana paius': '14.09.2005',
    'ziynet igdedali': '25.12.1996',
    'yohannes kifle': '10.08.1991',
    'perla demirova': '16.08.2004',
    'dzhanan ahmedova': '26.12.2005',
    'antonia adamova': '30.01.2006',
    'doris adzamic': '13.10.2000',
    'gizem polat': '08.05.2000',
    'loreen sophie gawlitza': '28.07.2001',
    'marla lange': '15.12.2004',
    'salsabila iminwarek': '28.02.2002',
    'marie krass': '06.12.2001',
    'ernis danjolli': '03.10.2000',
    'connor filsinger': '08.01.2003',
    'michelle brettschneider': '28.03.2001',
    'michelle cheyenne brettschneider': '28.03.2001',
    'issam boulahri': '23.11.1997',
    'dilan kalkan': '08.10.1997',
    'andre richie kingue': '24.02.2007',
    'ines jordan': '05.09.1990',
    'ksenia marszalek': '18.07.1979',
    'fatemehr bagheri hosseinabadi': '04.03.2000',
    'shahrzad bagher': '04.03.2000',
    'akeel zafar': '25.05.1995',
    'julius degen': '24.10.2007',
    'mariatou camara': '02.06.2000',
    'katerina gentsou': '14.06.1998',
    'marzia islam': '17.04.1996',
    'musa jamali': '14.10.1991',
    'claire odinius': '20.05.2008',
    'simon porscke': '30.05.2008',
    'simon poerschke': '30.05.2008',
    'simon pörschke': '30.05.2008',
    'maximilian richter': '20.07.2008',
    'antor shaha': '07.03.1997',
    'simret solomon': '04.08.1977',
    'izabella somodi': '31.08.2001',
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


def seed_birth_dates(apps, schema_editor):
    WorkerProfile = apps.get_model('core', 'WorkerProfile')
    EmployeeMasterData = apps.get_model('core', 'EmployeeMasterData')

    for worker in WorkerProfile.objects.select_related('user').all():
        full_name = normalise(f'{worker.user.first_name} {worker.user.last_name}')
        birth_date = BIRTH_DATES.get(full_name)
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


def unseed_birth_dates(apps, schema_editor):
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
        ('core', '0042_shift_plan_documents'),
    ]

    operations = [
        migrations.RunPython(seed_birth_dates, unseed_birth_dates),
    ]
