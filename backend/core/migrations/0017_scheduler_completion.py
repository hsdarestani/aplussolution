import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('core', '0016_custom_reporting')]

    operations = [
        migrations.CreateModel(
            name='SchedulerCompletionSettings',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('allow_overlapping_open_shifts', models.BooleanField(default=False)),
                ('require_shift_confirmation', models.BooleanField(default=True)),
            ],
            options={'verbose_name_plural': 'Scheduler completion settings'},
        ),
        migrations.CreateModel(
            name='SchedulerColorOverride',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('target_type', models.CharField(choices=[('shift', 'Schicht'), ('location', 'Einsatzort / Job Site')], max_length=20)),
                ('target_id', models.UUIDField()),
                ('color', models.CharField(default='#2457E6', max_length=20)),
            ],
            options={
                'ordering': ['target_type', 'target_id'],
                'indexes': [models.Index(fields=['target_type', 'target_id'], name='sched_color_target_idx')],
                'unique_together': {('target_type', 'target_id')},
            },
        ),
        migrations.CreateModel(
            name='SchedulerDisplayPreference',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('color_mode', models.CharField(choices=[('shift', 'Schichtfarbe'), ('position', 'Position'), ('location', 'Einsatzort / Job Site')], default='position', max_length=20)),
                ('timezone_mode', models.CharField(choices=[('workplace', 'Betriebszeitzone'), ('schedule', 'Dienstplan-Zeitzone'), ('local', 'Lokale Zeitzone')], default='workplace', max_length=20)),
                ('local_timezone', models.CharField(default='Europe/Berlin', max_length=64)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='scheduler_display_preference', to='core.user')),
            ],
        ),
        migrations.CreateModel(
            name='ScheduleAnnotation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('kind', models.CharField(choices=[('announcement', 'Ankündigung'), ('business_closed', 'Betrieb geschlossen'), ('block_time_off', 'Keine Abwesenheit zulassen')], default='announcement', max_length=30)),
                ('title', models.CharField(max_length=180)),
                ('message', models.TextField(blank=True)),
                ('starts_on', models.DateField()),
                ('ends_on', models.DateField()),
                ('business_closed_action', models.CharField(choices=[('leave', 'Schichten unverändert lassen'), ('unpublish', 'Unbelegte Schichten zurückziehen'), ('open', 'Belegte Schichten als OpenShift freigeben'), ('delete', 'Zukünftige Schichten löschen')], default='leave', max_length=20)),
                ('active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_annotations_created', to='core.user')),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='schedule_annotations', to='core.location')),
                ('schedule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='annotations', to='core.schedulegroup')),
            ],
            options={
                'ordering': ['starts_on', 'title'],
                'indexes': [models.Index(fields=['active', 'starts_on', 'ends_on'], name='sched_annot_range_idx')],
            },
        ),
        migrations.CreateModel(
            name='ScheduleTaskList',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=180)),
                ('work_date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_task_lists_created', to='core.user')),
                ('location', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='schedule_task_lists', to='core.location')),
                ('schedule', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='task_lists', to='core.schedulegroup')),
            ],
            options={
                'ordering': ['work_date', 'title'],
                'indexes': [models.Index(fields=['active', 'work_date'], name='sched_tasklist_date_idx')],
            },
        ),
        migrations.CreateModel(
            name='ScheduleTask',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=220)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('assignee', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_tasks', to='core.workerprofile')),
                ('completed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_tasks_completed', to='core.user')),
                ('position', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='schedule_tasks', to='core.position')),
                ('task_list', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='tasks', to='core.scheduletasklist')),
            ],
            options={
                'ordering': ['sort_order', 'created_at'],
                'indexes': [models.Index(fields=['assignee', 'completed_at'], name='sched_task_assignee_idx')],
            },
        ),
        migrations.CreateModel(
            name='ShiftConfirmation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('publication_at', models.DateTimeField(blank=True, null=True)),
                ('requested_at', models.DateTimeField()),
                ('confirmed_at', models.DateTimeField(blank=True, null=True)),
                ('confirmed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='shift_confirmations_completed', to='core.user')),
                ('shift', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='confirmations', to='core.shift')),
                ('slot', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='confirmation', to='core.shiftslot')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shift_confirmations', to='core.workerprofile')),
            ],
            options={
                'ordering': ['shift__starts_at', 'worker__employee_number'],
                'indexes': [models.Index(fields=['worker', 'confirmed_at'], name='shift_confirm_worker_idx')],
            },
        ),
    ]
