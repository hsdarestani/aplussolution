from django.db import migrations


def seed_defaults(apps, schema_editor):
    SchedulingPolicy = apps.get_model('core', 'SchedulingPolicy')
    TimeOffCategory = apps.get_model('core', 'TimeOffCategory')
    if not SchedulingPolicy.objects.filter(active=True).exists():
        SchedulingPolicy.objects.create(name='Standard')
    defaults = [
        ('Urlaub', 'vacation', True, True),
        ('Krankheit', 'sick', True, True),
        ('Feiertag', 'holiday', True, False),
        ('Unbezahlt', 'unpaid', False, True),
        ('Sonstige Abwesenheit', 'other', False, True),
    ]
    for name, code, paid, approval in defaults:
        TimeOffCategory.objects.get_or_create(
            code=code,
            defaults={'name': name, 'paid': paid, 'requires_approval': approval, 'active': True},
        )


def reverse_defaults(apps, schema_editor):
    TimeOffCategory = apps.get_model('core', 'TimeOffCategory')
    TimeOffCategory.objects.filter(code__in=['vacation', 'sick', 'holiday', 'unpaid', 'other']).delete()


class Migration(migrations.Migration):
    dependencies = [('core', '0009_premium_approval_and_labor_sharing')]
    operations = [migrations.RunPython(seed_defaults, reverse_defaults)]
