from datetime import date

from django.db import migrations, models
import django.db.models.deletion
import uuid


DEFAULTS = {
    'permit_date': date(2024, 4, 15),
    'framework_date': date(2024, 8, 26),
    'required_qualification': 'Serviceerfahrung in der Gastronomie',
    'intended_activity': 'Servicetätigkeiten – Eventcatering',
}


def seed_defaults(apps, schema_editor):
    AuevSetting = apps.get_model('core', 'AuevSetting')
    if not AuevSetting.objects.filter(client__isnull=True).exists():
        AuevSetting.objects.create(**DEFAULTS)


def remove_defaults(apps, schema_editor):
    AuevSetting = apps.get_model('core', 'AuevSetting')
    AuevSetting.objects.filter(client__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0043_seed_employee_birth_dates'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuevSetting',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('permit_date', models.DateField(blank=True, null=True)),
                ('framework_date', models.DateField(blank=True, null=True)),
                ('effective_date', models.DateField(blank=True, null=True)),
                ('required_qualification', models.CharField(blank=True, max_length=255)),
                ('intended_activity', models.CharField(blank=True, max_length=255)),
                ('client', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='auev_setting', to='core.clientcompany')),
            ],
        ),
        migrations.RunPython(seed_defaults, remove_defaults),
    ]
