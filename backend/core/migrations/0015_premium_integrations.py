import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0014_communications_v6')]

    operations = [
        migrations.CreateModel(
            name='IntegrationApiKey',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=160)),
                ('prefix', models.CharField(db_index=True, max_length=20, unique=True)),
                ('secret_hash', models.CharField(max_length=255)),
                ('scopes', models.JSONField(blank=True, default=list)),
                ('active', models.BooleanField(default=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('last_used_at', models.DateTimeField(blank=True, null=True)),
                ('revoked_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='integration_api_keys_created', to='core.user')),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='SamlIdentityProvider',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(default='Company SSO', max_length=160)),
                ('enabled', models.BooleanField(default=False)),
                ('sp_entity_id', models.CharField(blank=True, max_length=300)),
                ('idp_entity_id', models.CharField(max_length=300)),
                ('sso_url', models.URLField(max_length=500)),
                ('x509_certificate', models.TextField()),
                ('allowed_domains', models.JSONField(blank=True, default=list)),
                ('auto_provision', models.BooleanField(default=False)),
                ('default_role', models.CharField(choices=[('admin', 'Administration'), ('manager', 'Disposition'), ('worker', 'Mitarbeiter'), ('client', 'Kunde')], default='worker', max_length=20)),
                ('updated_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='saml_settings_updated', to='core.user')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='SamlLoginRequest',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('request_id', models.CharField(db_index=True, max_length=80, unique=True)),
                ('target', models.CharField(default='/', max_length=500)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('provider', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='login_requests', to='core.samlidentityprovider')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['provider', 'expires_at', 'used_at'], name='saml_login_request_idx')],
            },
        ),
        migrations.CreateModel(
            name='WebhookSubscription',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=160)),
                ('url', models.URLField(max_length=500)),
                ('secret_encrypted', models.TextField()),
                ('event_types', models.JSONField(blank=True, default=list)),
                ('active', models.BooleanField(default=True)),
                ('timeout_seconds', models.PositiveSmallIntegerField(default=10)),
                ('max_attempts', models.PositiveSmallIntegerField(default=6)),
                ('last_success_at', models.DateTimeField(blank=True, null=True)),
                ('last_failure_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='webhook_subscriptions_created', to='core.user')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='PayrollConnector',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=160)),
                ('provider', models.CharField(choices=[('datev_csv', 'DATEV CSV'), ('generic_json', 'Generic JSON API')], max_length=30)),
                ('configuration', models.JSONField(blank=True, default=dict)),
                ('credentials_encrypted', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True)),
                ('last_export_at', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payroll_connectors_created', to='core.user')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='WebhookDelivery',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event_id', models.UUIDField(default=uuid.uuid4)),
                ('event_type', models.CharField(max_length=120)),
                ('payload', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('pending', 'Ausstehend'), ('retry', 'Wiederholung'), ('delivered', 'Zugestellt'), ('dead', 'Dead Letter')], default='pending', max_length=20)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('next_attempt_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('last_http_status', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('last_error', models.TextField(blank=True)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='core.webhooksubscription')),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['status', 'next_attempt_at'], name='webhook_delivery_due_idx')],
                'constraints': [models.UniqueConstraint(fields=('subscription', 'event_id'), name='webhook_delivery_unique_event')],
            },
        ),
        migrations.CreateModel(
            name='PayrollExportRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('status', models.CharField(choices=[('running', 'Läuft'), ('success', 'Erfolgreich'), ('failed', 'Fehlgeschlagen')], default='running', max_length=20)),
                ('record_count', models.PositiveIntegerField(default=0)),
                ('checksum', models.CharField(blank=True, max_length=64)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('connector', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='exports', to='core.payrollconnector')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='payroll_exports_created', to='core.user')),
                ('pay_period', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='integration_exports', to='core.payperiod')),
            ],
            options={
                'ordering': ['-created_at'],
                'constraints': [models.UniqueConstraint(fields=('connector', 'pay_period'), name='payroll_connector_period_unique')],
            },
        ),
    ]
