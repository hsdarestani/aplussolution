import uuid

import django.db.models.deletion
from django.db import migrations, models


def seed_default_policy(apps, schema_editor):
    Policy = apps.get_model('core', 'SchedulingPolicy')
    Policy.objects.get_or_create(
        name='A+ Standard',
        defaults={
            'min_rest_hours': 11,
            'max_days_per_week': 6,
            'max_consecutive_days': 6,
            'max_weekly_hours': 48,
            'qualification_mode': 'warn',
            'schedule_membership_mode': 'off',
            'skill_tag_mode': 'warn',
            'availability_mode': 'block',
            'time_off_mode': 'block',
            'rest_mode': 'warn',
            'hours_mode': 'warn',
            'days_mode': 'warn',
            'active': True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [('core', '0007_seed_store_reviewer')]

    operations = [
        migrations.CreateModel(
            name='ScheduleGroup',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=160, unique=True)),
                ('timezone', models.CharField(default='Europe/Berlin', max_length=64)),
                ('active', models.BooleanField(default=True)),
                ('locations', models.ManyToManyField(blank=True, related_name='schedule_groups', to='core.location')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='SkillTag',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=120, unique=True)),
                ('color', models.CharField(default='#155eef', max_length=20)),
                ('active', models.BooleanField(default=True)),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='ScheduleTemplate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=180)),
                ('active', models.BooleanField(default=True)),
                ('notes', models.TextField(blank=True)),
                ('schedule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='templates', to='core.schedulegroup')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='ScheduleMembership',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('active', models.BooleanField(default=True)),
                ('primary', models.BooleanField(default=False)),
                ('schedule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='core.schedulegroup')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_memberships', to='core.workerprofile')),
            ],
            options={'ordering': ['schedule__name', 'worker__employee_number'], 'unique_together': {('schedule', 'worker')}},
        ),
        migrations.CreateModel(
            name='WorkerPositionQualification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('level', models.CharField(choices=[('trainee', 'In Einarbeitung'), ('qualified', 'Qualifiziert'), ('lead', 'Leitung')], default='qualified', max_length=20)),
                ('active', models.BooleanField(default=True)),
                ('expires_on', models.DateField(blank=True, null=True)),
                ('note', models.CharField(blank=True, max_length=250)),
                ('position', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='worker_qualifications', to='core.position')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='position_qualifications', to='core.workerprofile')),
            ],
            options={'ordering': ['worker__employee_number', 'position__name'], 'unique_together': {('worker', 'position')}},
        ),
        migrations.CreateModel(
            name='WorkerSkillTag',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('verified', models.BooleanField(default=True)),
                ('expires_on', models.DateField(blank=True, null=True)),
                ('note', models.CharField(blank=True, max_length=250)),
                ('tag', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='worker_links', to='core.skilltag')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='skill_tags', to='core.workerprofile')),
            ],
            options={'ordering': ['worker__employee_number', 'tag__name'], 'unique_together': {('worker', 'tag')}},
        ),
        migrations.CreateModel(
            name='PositionSkillTag',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('required', models.BooleanField(default=True)),
                ('position', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='required_tag_links', to='core.position')),
                ('tag', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='position_links', to='core.skilltag')),
            ],
            options={'ordering': ['position__name', 'tag__name'], 'unique_together': {('position', 'tag')}},
        ),
        migrations.CreateModel(
            name='SchedulingPolicy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=160, unique=True)),
                ('active', models.BooleanField(default=True)),
                ('min_rest_hours', models.DecimalField(decimal_places=2, default=11, max_digits=5)),
                ('max_days_per_week', models.PositiveSmallIntegerField(default=6)),
                ('max_consecutive_days', models.PositiveSmallIntegerField(default=6)),
                ('max_weekly_hours', models.DecimalField(decimal_places=2, default=48, max_digits=6)),
                ('qualification_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='warn', max_length=10)),
                ('schedule_membership_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='off', max_length=10)),
                ('skill_tag_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='warn', max_length=10)),
                ('availability_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='block', max_length=10)),
                ('time_off_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='block', max_length=10)),
                ('rest_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='warn', max_length=10)),
                ('hours_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='warn', max_length=10)),
                ('days_mode', models.CharField(choices=[('off', 'Aus'), ('warn', 'Warnen'), ('block', 'Blockieren')], default='warn', max_length=10)),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scheduling_policies', to='core.location')),
                ('position', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scheduling_policies', to='core.position')),
                ('schedule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='policies', to='core.schedulegroup')),
            ],
            options={'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='ScheduleTemplateItem',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('weekday', models.PositiveSmallIntegerField(help_text='0=Montag, 6=Sonntag')),
                ('start_time', models.TimeField()),
                ('end_time', models.TimeField()),
                ('required_count', models.PositiveIntegerField(default=1)),
                ('break_minutes', models.PositiveIntegerField(default=0)),
                ('notes', models.TextField(blank=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_template_items', to='core.clientcompany')),
                ('location', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_template_items', to='core.location')),
                ('position', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedule_template_items', to='core.position')),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='core.scheduletemplate')),
            ],
            options={'ordering': ['weekday', 'start_time']},
        ),
        migrations.RunPython(seed_default_policy, migrations.RunPython.noop),
    ]
