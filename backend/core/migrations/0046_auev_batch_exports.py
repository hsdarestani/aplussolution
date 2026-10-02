from datetime import date

from django.db import migrations, models
import django.db.models.deletion
import uuid


def seed_known_customer_patterns(apps, schema_editor):
    ClientCompany = apps.get_model('core', 'ClientCompany')
    AuevSetting = apps.get_model('core', 'AuevSetting')

    default = AuevSetting.objects.filter(client__isnull=True).first()
    if default and default.permit_date == date(2024, 4, 15):
        default.permit_date = date(2025, 4, 20)
        default.save(update_fields=['permit_date', 'updated_at'])

    for client in ClientCompany.objects.all():
        name = (client.name or '').casefold()
        values = None
        if 'stadthaus' in name or 'lectron' in name:
            values = {
                'file_label': 'Stadthaus am Markt',
                'last_sequence_number': 6,
                'framework_date': date(2026, 5, 12),
                'effective_date': date(2026, 5, 21),
                'intended_activity': 'Servicekraft',
            }
        elif 'hirschgarten' in name:
            values = {
                'file_label': 'Restaurant HirschGarten',
                'last_sequence_number': 3,
                'framework_date': date(2026, 4, 17),
                'effective_date': date(2026, 6, 6),
                'intended_activity': 'Servicekraft',
            }
        elif 'manuel höfel' in name or 'manuel hoefel' in name:
            values = {
                'file_label': 'Manuel Höfel',
                'last_sequence_number': 2,
                'framework_date': date(2026, 7, 24),
                'effective_date': date(2026, 8, 1),
                'intended_activity': 'Servicekraft',
            }
        if not values:
            continue

        row, _ = AuevSetting.objects.get_or_create(client=client)
        changed = []
        for field, value in values.items():
            current = getattr(row, field, None)
            if current in (None, '', 0):
                setattr(row, field, value)
                changed.append(field)
        if changed:
            row.save(update_fields=changed + ['updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0045_hide_auev_from_customer_portal'),
    ]

    operations = [
        migrations.AddField(
            model_name='auevsetting',
            name='client_contract_text',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='auevsetting',
            name='file_label',
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name='auevsetting',
            name='last_sequence_number',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='AuevExport',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('template_key', models.CharField(choices=[('classic', 'Klassisch'), ('new', 'Neu')], default='classic', max_length=20)),
                ('date_from', models.DateField()),
                ('date_to', models.DateField()),
                ('first_shift_date', models.DateField()),
                ('last_shift_date', models.DateField()),
                ('signature_date', models.DateField()),
                ('sequence_number', models.PositiveIntegerField()),
                ('calendar_weeks', models.JSONField(blank=True, default=list)),
                ('settings_snapshot', models.JSONField(blank=True, default=dict)),
                ('shift_ids', models.JSONField(blank=True, default=list)),
                ('row_count', models.PositiveIntegerField(default=0)),
                ('file_stem', models.CharField(max_length=255)),
                ('docx', models.FileField(upload_to='auev_exports/%Y/%m/')),
                ('pdf', models.FileField(upload_to='auev_exports/%Y/%m/')),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='auev_exports', to='core.clientcompany')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_auev_exports', to='core.user')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='auevexport',
            constraint=models.UniqueConstraint(fields=('client', 'sequence_number'), name='unique_auev_sequence_per_client'),
        ),
        migrations.RunPython(seed_known_customer_patterns, migrations.RunPython.noop),
    ]
