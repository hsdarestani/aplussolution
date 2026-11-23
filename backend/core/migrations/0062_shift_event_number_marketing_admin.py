"""Add explicit event numbers and provision the requested marketing admin.

Existing notes remain untouched. The new super-admin has an unusable password
if newly created: a verified owner must set a password through the normal reset
flow. An existing marketing account keeps its current password.
"""
import re

from django.contrib.auth.hashers import make_password
from django.db import migrations, models


REFERENCE = re.compile(
    r'\b(?:event(?:\s*[-/.]?\s*(?:nr\.?|nummer|number|no\.?|id))?'
    r'|veranstaltung(?:s(?:nummer|nr\.?)|\s*(?:nr\.?|nummer|id))?'
    r'|va\s*[-/.]?\s*(?:nr\.?|nummer|id)'
    r'|auftrags?\s*[-/.]?\s*(?:nr\.?|nummer)'
    r'|evt\s*[-/.]?\s*(?:nr\.?|id)?)'
    r'\s*[:#=\-]?\s*#?\s*([A-Z]{0,5}[-/]?\d{2,12}(?:[-/]\d{1,5})?)\b',
    re.IGNORECASE,
)
NUMBER_LINE = re.compile(
    r'(?:^|[\r\n])\s*(?:nr|nummer)\.?\s*[:#=\-]?\s*#?\s*(\d{2,12})\b',
    re.IGNORECASE | re.MULTILINE,
)
NUMBER_ONLY = re.compile(r'^\s*#?\s*(\d{3,12})\s*$')


def backfill_event_numbers(apps, schema_editor):
    Shift = apps.get_model('core', 'Shift')
    db_alias = schema_editor.connection.alias
    changes = []
    for shift in Shift.objects.using(db_alias).filter(event_number='').exclude(notes='').iterator(chunk_size=500):
        value = str(shift.notes or '')
        found = REFERENCE.search(value) or NUMBER_LINE.search(value) or NUMBER_ONLY.fullmatch(value)
        if not found:
            continue
        number = found.group(1).strip().upper().replace(' ', '')
        if re.fullmatch(r'\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?', number):
            continue
        if number and len(number) <= 64:
            shift.event_number = number
            changes.append(shift)
        if len(changes) >= 500:
            Shift.objects.using(db_alias).bulk_update(changes, ['event_number'])
            changes.clear()
    if changes:
        Shift.objects.using(db_alias).bulk_update(changes, ['event_number'])


def provision_marketing_admin(apps, schema_editor):
    User = apps.get_model('core', 'User')
    qs = User.objects.using(schema_editor.connection.alias)
    email = 'marketing@aplus-solution.de'
    existing = qs.filter(email__iexact=email).first()
    if existing is None:
        qs.create(
            email=email,
            username=email,
            password=make_password(None),
            role='admin',
            is_staff=True,
            is_superuser=True,
            is_active=True,
            is_onboarded=True,
        )
    else:
        existing.role = 'admin'
        existing.is_staff = True
        existing.is_superuser = True
        existing.is_active = True
        existing.is_onboarded = True
        existing.save(update_fields=[
            'role', 'is_staff', 'is_superuser', 'is_active', 'is_onboarded',
        ])


class Migration(migrations.Migration):
    dependencies = [('core', '0061_worker_display_name')]
    operations = [
        migrations.AddField(
            model_name='shift',
            name='event_number',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.RunPython(backfill_event_numbers, migrations.RunPython.noop),
        migrations.RunPython(provision_marketing_admin, migrations.RunPython.noop),
    ]
