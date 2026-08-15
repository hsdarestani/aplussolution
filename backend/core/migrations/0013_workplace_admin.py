import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


ROLE_DATA = {
    'dispatcher': ('Disponent', ['manager.access','workplace.view','roles.view','people.view','people.edit','clients.view','clients.edit','schedule.view','schedule.edit','schedule.publish','attendance.view','attendance.edit','payroll.view','payroll.review','payroll.export','wage.view','labor.share','reports.view','documents.manage'], 'all'),
    'supervisor': ('Supervisor', ['manager.access','workplace.view','people.view','schedule.view','schedule.edit','schedule.publish','attendance.view','attendance.edit','payroll.view','payroll.review','wage.view','labor.share','reports.view'], 'scoped'),
    'scheduler': ('Dienstplaner', ['manager.access','people.view','schedule.view','schedule.edit','schedule.publish','labor.share'], 'none'),
    'payroll': ('Lohn & Zeiten', ['manager.access','people.view','attendance.view','attendance.edit','payroll.view','payroll.review','payroll.export','wage.view','reports.view'], 'all'),
    'viewer': ('Nur Lesen', ['manager.access','workplace.view','people.view','schedule.view','attendance.view','reports.view'], 'none'),
}


def seed_roles(apps, schema_editor):
    WorkplaceSettings = apps.get_model('core', 'WorkplaceSettings')
    AccessRole = apps.get_model('core', 'AccessRole')
    WorkplaceSettings.objects.get_or_create(company_name='A+ Solution GmbH')
    for code, (name, permissions, wage_visibility) in ROLE_DATA.items():
        AccessRole.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'description': '',
                'permissions': permissions,
                'wage_visibility': wage_visibility,
                'is_system': True,
                'active': True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [('core', '0012_pay_period_timesheets')]

    operations = [
        migrations.CreateModel(
            name='WorkplaceSettings',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_name', models.CharField(default='A+ Solution GmbH', max_length=180)),
                ('timezone', models.CharField(default='Europe/Berlin', max_length=64)),
                ('week_starts_on', models.PositiveSmallIntegerField(default=0, help_text='0=Montag, 6=Sonntag')),
                ('time_format', models.CharField(choices=[('24h', '24 Stunden'), ('12h', '12 Stunden')], default='24h', max_length=8)),
                ('currency', models.CharField(default='EUR', max_length=3)),
                ('overtime_daily_hours', models.DecimalField(decimal_places=2, default=Decimal('8.00'), max_digits=5)),
                ('overtime_weekly_hours', models.DecimalField(decimal_places=2, default=Decimal('40.00'), max_digits=6)),
                ('overtime_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='warn', max_length=10)),
                ('overtime_multiplier', models.DecimalField(decimal_places=2, default=Decimal('1.25'), max_digits=4)),
                ('labor_sharing_enabled', models.BooleanField(default=True)),
                ('manager_can_manage_roles', models.BooleanField(default=False)),
            ],
            options={'verbose_name_plural': 'Workplace settings'},
        ),
        migrations.CreateModel(
            name='AccessRole',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.SlugField(max_length=80, unique=True)),
                ('name', models.CharField(max_length=140)),
                ('description', models.TextField(blank=True)),
                ('permissions', models.JSONField(blank=True, default=list)),
                ('wage_visibility', models.CharField(choices=[('none', 'Keine'), ('scoped', 'Nur eigener Bereich'), ('all', 'Alle')], default='none', max_length=10)),
                ('is_system', models.BooleanField(default=False)),
                ('active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='UserAccessAssignment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('scope_mode', models.CharField(choices=[('all', 'Gesamter Betrieb'), ('scoped', 'Zugeordnete Bereiche')], default='scoped', max_length=10)),
                ('can_share_labor', models.BooleanField(default=False)),
                ('active', models.BooleanField(default=True)),
                ('access_role', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='assignments', to='core.accessrole')),
                ('locations', models.ManyToManyField(blank=True, related_name='access_assignments', to='core.location')),
                ('schedule_groups', models.ManyToManyField(blank=True, related_name='access_assignments', to='core.schedulegroup')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='access_assignment', to=settings.AUTH_USER_MODEL)),
                ('workers', models.ManyToManyField(blank=True, related_name='supervisor_assignments', to='core.workerprofile')),
            ],
            options={'ordering': ['user__first_name', 'user__last_name', 'user__email']},
        ),
        migrations.RunPython(seed_roles, migrations.RunPython.noop),
    ]
