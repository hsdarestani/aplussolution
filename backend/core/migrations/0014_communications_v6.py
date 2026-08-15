import uuid

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def backfill_communications(apps, schema_editor):
    Notification = apps.get_model('core', 'Notification')
    NotificationState = apps.get_model('core', 'NotificationState')
    Conversation = apps.get_model('core', 'Conversation')
    ConversationChannel = apps.get_model('core', 'ConversationChannel')
    ConversationMembership = apps.get_model('core', 'ConversationMembership')
    CommunicationSettings = apps.get_model('core', 'CommunicationSettings')

    CommunicationSettings.objects.get_or_create()
    for item in Notification.objects.all().iterator():
        NotificationState.objects.get_or_create(
            notification_id=item.pk,
            defaults={'category': 'workplace', 'dedupe_key': item.kind or '', 'data': {'legacy_backfill': True}},
        )
    for conversation in Conversation.objects.all().iterator():
        ConversationChannel.objects.get_or_create(
            conversation_id=conversation.pk,
            defaults={'channel_type': 'group', 'active': True, 'pinned': False},
        )
        for user_id in conversation.participants.values_list('id', flat=True):
            ConversationMembership.objects.get_or_create(
                conversation_id=conversation.pk,
                user_id=user_id,
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('core', '0013_workplace_admin')]

    operations = [
        migrations.CreateModel(
            name='CommunicationSettings',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('workchat_enabled', models.BooleanField(default=True)),
                ('employees_can_post_workplace', models.BooleanField(default=False)),
                ('users_can_create_channels', models.BooleanField(default=False)),
                ('images_enabled', models.BooleanField(default=True)),
                ('sms_fallback_enabled', models.BooleanField(default=False)),
            ],
        ),
        migrations.CreateModel(
            name='ConversationChannel',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('channel_type', models.CharField(choices=[('workplace', 'Betrieb'), ('group', 'Gruppe'), ('direct', 'Direkt')], default='group', max_length=16)),
                ('active', models.BooleanField(default=True)),
                ('pinned', models.BooleanField(default=False)),
                ('conversation', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='channel', to='core.conversation')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_workchat_channels', to='core.user')),
            ],
            options={'indexes': [models.Index(fields=['channel_type', 'active'], name='chat_channel_type_active_idx')]},
        ),
        migrations.CreateModel(
            name='DeviceRegistration',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('token', models.CharField(max_length=512, unique=True)),
                ('platform', models.CharField(choices=[('ios', 'iOS'), ('android', 'Android'), ('web', 'Web')], max_length=16)),
                ('device_name', models.CharField(blank=True, max_length=160)),
                ('active', models.BooleanField(default=True)),
                ('last_seen_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('app_version', models.CharField(blank=True, max_length=40)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='push_devices', to='core.user')),
            ],
            options={'indexes': [models.Index(fields=['user', 'active'], name='device_user_active_idx')]},
        ),
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.CharField(choices=[('time_off', 'Abwesenheitsanträge'), ('swap_drop', 'Tausch / Abgabe'), ('open_shift', 'Offene Schichten'), ('absence', 'Abwesenheiten'), ('schedule_update', 'Dienstplanänderungen'), ('new_user', 'Neue Benutzer'), ('availability', 'Verfügbarkeitsänderungen'), ('clock_reminder', 'Ein-/Ausstempel-Erinnerungen'), ('overtime', 'Überstunden'), ('payroll', 'Abrechnung'), ('reports', 'Berichte'), ('workplace', 'Betriebsmitteilungen'), ('shift_reminder', 'Schichterinnerungen'), ('workchat', 'WorkChat')], max_length=40)),
                ('in_app_enabled', models.BooleanField(default=True)),
                ('push_enabled', models.BooleanField(default=True)),
                ('email_enabled', models.BooleanField(default=True)),
                ('sms_enabled', models.BooleanField(default=False)),
                ('reminder_minutes', models.PositiveIntegerField(default=1440)),
                ('dnd_start', models.TimeField(blank=True, null=True)),
                ('dnd_end', models.TimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_preferences', to='core.user')),
            ],
            options={
                'ordering': ['category'],
                'constraints': [models.UniqueConstraint(fields=('user', 'category'), name='uniq_notification_pref_user_category')],
            },
        ),
        migrations.CreateModel(
            name='ConversationMembership',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('role', models.CharField(choices=[('owner', 'Owner'), ('moderator', 'Moderator'), ('member', 'Mitglied')], default='member', max_length=16)),
                ('notifications_enabled', models.BooleanField(default=True)),
                ('muted', models.BooleanField(default=False)),
                ('joined_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('left_at', models.DateTimeField(blank=True, null=True)),
                ('last_read_at', models.DateTimeField(blank=True, null=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='channel_memberships', to='core.conversation')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='channel_memberships', to='core.user')),
            ],
            options={
                'indexes': [models.Index(fields=['user', 'left_at'], name='chat_member_user_left_idx')],
                'constraints': [models.UniqueConstraint(fields=('conversation', 'user'), name='uniq_chat_membership_user')],
            },
        ),
        migrations.CreateModel(
            name='MessageState',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('edited_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deleted_chat_messages', to='core.user')),
                ('message', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='message_state', to='core.message')),
            ],
        ),
        migrations.CreateModel(
            name='NotificationState',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.CharField(choices=[('time_off', 'Abwesenheitsanträge'), ('swap_drop', 'Tausch / Abgabe'), ('open_shift', 'Offene Schichten'), ('absence', 'Abwesenheiten'), ('schedule_update', 'Dienstplanänderungen'), ('new_user', 'Neue Benutzer'), ('availability', 'Verfügbarkeitsänderungen'), ('clock_reminder', 'Ein-/Ausstempel-Erinnerungen'), ('overtime', 'Überstunden'), ('payroll', 'Abrechnung'), ('reports', 'Berichte'), ('workplace', 'Betriebsmitteilungen'), ('shift_reminder', 'Schichterinnerungen'), ('workchat', 'WorkChat')], default='workplace', max_length=40)),
                ('priority', models.CharField(choices=[('low', 'Niedrig'), ('normal', 'Normal'), ('high', 'Hoch'), ('urgent', 'Dringend')], default='normal', max_length=12)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('data', models.JSONField(blank=True, default=dict)),
                ('dedupe_key', models.CharField(blank=True, db_index=True, max_length=180)),
                ('delivery_enqueued_at', models.DateTimeField(blank=True, null=True)),
                ('notification', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='delivery_state', to='core.notification')),
            ],
            options={'indexes': [
                models.Index(fields=['category', 'read_at'], name='notif_state_category_read_idx'),
                models.Index(fields=['deleted_at', 'created_at'], name='notif_state_del_created_idx'),
            ]},
        ),
        migrations.CreateModel(
            name='NotificationDelivery',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('channel', models.CharField(choices=[('push', 'Push'), ('email', 'E-Mail'), ('sms', 'SMS')], max_length=12)),
                ('status', models.CharField(choices=[('pending', 'Ausstehend'), ('sent', 'Gesendet'), ('skipped', 'Übersprungen'), ('failed', 'Fehlgeschlagen')], default='pending', max_length=16)),
                ('provider', models.CharField(blank=True, max_length=40)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('error', models.TextField(blank=True)),
                ('provider_response', models.JSONField(blank=True, default=dict)),
                ('notification', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='delivery_attempts', to='core.notification')),
            ],
            options={'constraints': [models.UniqueConstraint(fields=('notification', 'channel'), name='uniq_notification_delivery_channel')]},
        ),
        migrations.RunPython(backfill_communications, noop_reverse),
    ]
