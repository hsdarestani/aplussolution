import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0009_forecast_tools')]

    operations = [
        migrations.CreateModel(
            name='ShiftAbsenceCase',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('sick', 'Krank'), ('emergency', 'Notfall'), ('personal', 'Persönlich verhindert'), ('no_show', 'Nicht erschienen'), ('approved_time_off', 'Genehmigte Abwesenheit'), ('other', 'Sonstiger Ausfall')], default='other', max_length=30)),
                ('source', models.CharField(choices=[('worker', 'Mitarbeiter'), ('manager', 'Disposition'), ('time_off', 'Abwesenheitsantrag'), ('attendance', 'Zeiterfassung'), ('system', 'System')], default='worker', max_length=30)),
                ('status', models.CharField(choices=[('reported', 'Gemeldet'), ('coverage_pending', 'Ersatz offen'), ('offered', 'Angebote versendet'), ('moved_to_open', 'Als OpenShift veröffentlicht'), ('covered', 'Ersatz gefunden'), ('resolved_uncovered', 'Ohne Ersatz abgeschlossen'), ('cancelled', 'Storniert')], default='reported', max_length=30)),
                ('coverage_strategy', models.CharField(choices=[('none', 'Noch nicht gewählt'), ('open_shift', 'OpenShift'), ('targeted', 'Gezielte Ersatzanfrage'), ('direct', 'Direkte Ersatzbesetzung')], default='none', max_length=30)),
                ('reason_note', models.TextField(blank=True)),
                ('manager_note', models.TextField(blank=True)),
                ('short_notice', models.BooleanField(default=False)),
                ('reported_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('absent_worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='absence_cases', to='core.workerprofile')),
                ('replacement_worker', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='replacement_cases', to='core.workerprofile')),
                ('reported_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reported_absence_cases', to=settings.AUTH_USER_MODEL)),
                ('resolved_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_absence_cases', to=settings.AUTH_USER_MODEL)),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='absence_cases', to='core.shift')),
                ('slot', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='absence_cases', to='core.shiftslot')),
                ('time_off_request', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='absence_cases', to='core.timeoffrequest')),
            ],
            options={'ordering': ['-reported_at']},
        ),
        migrations.AddIndex(model_name='shiftabsencecase', index=models.Index(fields=['status', 'reported_at'], name='core_shifta_status_14be6e_idx')),
        migrations.AddIndex(model_name='shiftabsencecase', index=models.Index(fields=['shift', 'absent_worker'], name='core_shifta_shift_i_0e98d5_idx')),
        migrations.AddIndex(model_name='shiftabsencecase', index=models.Index(fields=['short_notice', 'status'], name='core_shifta_short_n_c1d960_idx')),
        migrations.CreateModel(
            name='CoverageOffer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending', 'Offen'), ('accepted', 'Angenommen'), ('declined', 'Abgelehnt'), ('cancelled', 'Storniert'), ('expired', 'Abgelaufen')], default='pending', max_length=20)),
                ('offered_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('eligibility_snapshot', models.JSONField(blank=True, default=dict)),
                ('note', models.CharField(blank=True, max_length=250)),
                ('case', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offers', to='core.shiftabsencecase')),
                ('offered_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='coverage_offers_sent', to=settings.AUTH_USER_MODEL)),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coverage_offers', to='core.workerprofile')),
            ],
            options={'ordering': ['-offered_at'], 'unique_together': {('case', 'worker')}},
        ),
        migrations.AddIndex(model_name='coverageoffer', index=models.Index(fields=['worker', 'status', 'expires_at'], name='core_covera_worker__fb45fa_idx')),
    ]
