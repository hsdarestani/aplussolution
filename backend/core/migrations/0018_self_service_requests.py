import uuid
from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


def seed_self_service(apps, schema_editor):
    Settings = apps.get_model('core', 'SelfServiceSettings')
    TimeOffType = apps.get_model('core', 'TimeOffType')
    Settings.objects.get_or_create()
    defaults = [
        ('holiday', 'Urlaub', 'holiday', True, True, False, False),
        ('personal', 'Persönlich', 'personal', True, True, False, False),
        ('sick', 'Krank', 'sick', True, True, True, True),
    ]
    for code, name, kind, allow_paid, allow_unpaid, allow_past, ignores_notice in defaults:
        TimeOffType.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'kind': kind,
                'allow_paid': allow_paid,
                'allow_unpaid': allow_unpaid,
                'allow_past': allow_past,
                'ignores_notice': ignores_notice,
                'active': True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [('core', '0017_scheduler_completion')]

    operations = [
        migrations.CreateModel(
            name='SelfServiceSettings',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('availability_enabled', models.BooleanField(default=True)),
                ('show_availability_to_all', models.BooleanField(default=False)),
                ('availability_notice_days', models.PositiveSmallIntegerField(default=0)),
                ('team_schedule_visibility', models.CharField(choices=[('none', 'Nur eigene Schichten'), ('positions', 'Gemeinsame Positionen'), ('all', 'Gesamter Team-Dienstplan')], default='none', max_length=20)),
                ('global_user_privacy', models.BooleanField(default=False)),
                ('allow_shift_release', models.BooleanField(default=True)),
                ('release_cutoff_hours', models.PositiveSmallIntegerField(default=0)),
                ('allow_shift_drop', models.BooleanField(default=True)),
                ('drop_cutoff_hours', models.PositiveSmallIntegerField(default=0)),
                ('allow_shift_swap', models.BooleanField(default=True)),
                ('swap_cutoff_hours', models.PositiveSmallIntegerField(default=0)),
                ('require_manager_review_swaps_drops', models.BooleanField(default=True)),
                ('time_off_enabled', models.BooleanField(default=True)),
                ('time_off_notice_days', models.PositiveSmallIntegerField(default=0)),
                ('time_off_max_paid_hours_per_day', models.DecimalField(decimal_places=2, default=Decimal('8.00'), max_digits=5)),
            ],
            options={'verbose_name_plural': 'Self-service settings'},
        ),
        migrations.CreateModel(
            name='TimeOffType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.SlugField(max_length=60, unique=True)),
                ('name', models.CharField(max_length=120)),
                ('kind', models.CharField(choices=[('holiday', 'Urlaub'), ('personal', 'Persönlich'), ('sick', 'Krank'), ('custom', 'Benutzerdefiniert')], default='custom', max_length=20)),
                ('allow_paid', models.BooleanField(default=False)),
                ('allow_unpaid', models.BooleanField(default=True)),
                ('allow_past', models.BooleanField(default=False)),
                ('ignores_notice', models.BooleanField(default=False)),
                ('active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='UserSelfServicePreference',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('hide_contact_info', models.BooleanField(default=True)),
                ('preferred_weekly_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='self_service_preference', to='core.user')),
            ],
        ),
        migrations.CreateModel(
            name='AvailabilityPreferenceSeries',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('preferred', 'Bevorzugt'), ('unavailable', 'Nicht verfügbar')], max_length=20)),
                ('starts_on', models.DateField()),
                ('ends_on', models.DateField()),
                ('all_day', models.BooleanField(default=True)),
                ('start_time', models.TimeField(blank=True, null=True)),
                ('end_time', models.TimeField(blank=True, null=True)),
                ('recurrence', models.CharField(choices=[('once', 'Einmalig'), ('daily', 'Täglich'), ('weekly', 'Wöchentlich'), ('two_weeks', 'Alle 2 Wochen')], default='once', max_length=20)),
                ('weekdays', models.JSONField(blank=True, default=list)),
                ('note', models.CharField(blank=True, max_length=250)),
                ('active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='availability_series_created', to='core.user')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='availability_preference_series', to='core.workerprofile')),
            ],
            options={
                'ordering': ['starts_on', 'worker__employee_number'],
                'indexes': [models.Index(fields=['worker', 'active', 'starts_on', 'ends_on'], name='avail_series_range_idx')],
            },
        ),
        migrations.CreateModel(
            name='OpenShiftPolicy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('require_approval', models.BooleanField(default=False)),
                ('audience_mode', models.CharField(choices=[('eligible', 'Alle berechtigten Mitarbeiter'), ('selected', 'Ausgewählte Mitarbeiter')], default='eligible', max_length=20)),
                ('selected_workers', models.ManyToManyField(blank=True, related_name='targeted_open_shift_policies', to='core.workerprofile')),
                ('shift', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='open_shift_policy', to='core.shift')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='open_shift_policies_updated', to='core.user')),
            ],
        ),
        migrations.CreateModel(
            name='OpenShiftRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('pending_approval', 'Genehmigung ausstehend'), ('pending_acceptance', 'Annahme ausstehend'), ('accepted', 'Angenommen'), ('denied', 'Abgelehnt'), ('declined', 'Nicht angenommen'), ('canceled', 'Zurückgezogen'), ('expired', 'Abgelaufen')], default='pending_approval', max_length=30)),
                ('note', models.CharField(blank=True, max_length=500)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('decided_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='open_shift_requests_decided', to='core.user')),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='open_shift_requests', to='core.shift')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='open_shift_requests', to='core.workerprofile')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['status', 'created_at'], name='open_req_status_idx')],
                'unique_together': {('shift', 'worker')},
            },
        ),
        migrations.CreateModel(
            name='ShiftCoverageRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('drop', 'Schicht abgeben'), ('swap', 'Schicht tauschen')], max_length=20)),
                ('status', models.CharField(choices=[('pending_review', 'Manager-Prüfung ausstehend'), ('pending_acceptance', 'Annahme ausstehend'), ('accepted', 'Angenommen'), ('denied', 'Abgelehnt'), ('declined', 'Nicht angenommen'), ('canceled', 'Zurückgezogen'), ('expired', 'Abgelaufen')], max_length=30)),
                ('note', models.CharField(blank=True, max_length=500)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('offered_shift', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='swap_offers_received', to='core.shift')),
                ('offered_to', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='coverage_requests_received', to='core.workerprofile')),
                ('requested_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coverage_requests_created', to='core.workerprofile')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='coverage_requests_reviewed', to='core.user')),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coverage_requests', to='core.shift')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['status', 'created_at'], name='coverage_req_status_idx'),
                    models.Index(fields=['offered_to', 'status'], name='coverage_req_recipient_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='TimeOffRequestDetail',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('all_day', models.BooleanField(default=True)),
                ('start_time', models.TimeField(blank=True, null=True)),
                ('end_time', models.TimeField(blank=True, null=True)),
                ('paid', models.BooleanField(default=False)),
                ('paid_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True)),
                ('request', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='self_service_detail', to='core.timeoffrequest')),
                ('time_off_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='requests', to='core.timeofftype')),
            ],
        ),
        migrations.RunPython(seed_self_service, migrations.RunPython.noop),
    ]
