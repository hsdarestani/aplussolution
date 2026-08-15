from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.communications_models import (
    CommunicationSettings,
    ConversationChannel,
    DeviceRegistration,
    NotificationDelivery,
    NotificationPreference,
    NotificationState,
)
from core.communications_service import _send_sms, ensure_workplace_channel, get_preference
from core.models import Conversation, Notification, Shift, User, WorkerProfile
from core.workplace_models import AccessRole, UserAccessAssignment


pytestmark = pytest.mark.django_db


def auth(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_preferences_have_all_wiw_categories_and_workchat_defaults(auth_worker, worker_user):
    response = auth_worker.get('/api/notification-preferences/')
    assert response.status_code == 200
    rows = response.data
    assert len(rows) == len(NotificationPreference.Category.choices)
    workchat = next(row for row in rows if row['category'] == 'workchat')
    assert workchat['in_app_enabled'] is True
    assert workchat['push_enabled'] is True
    assert workchat['email_enabled'] is False
    assert workchat['sms_enabled'] is False
    reminder = next(row for row in rows if row['category'] == 'shift_reminder')
    changed = auth_worker.patch(
        f"/api/notification-preferences/{reminder['id']}/configure/",
        {'reminder_minutes': 30, 'email_enabled': False},
        format='json',
    )
    assert changed.status_code == 200
    assert changed.data['reminder_minutes'] == 30


def test_legacy_notification_gets_v6_state_and_center_supports_read_delete(auth_worker, worker_user):
    notification = Notification.objects.create(
        user=worker_user,
        kind='schedule-legacy-test',
        title='Dienstplan geändert',
        body='Neue Zeit',
        action_url='/schedule',
    )
    state = NotificationState.objects.get(notification=notification)
    assert state.category == NotificationPreference.Category.SCHEDULE
    listed = auth_worker.get('/api/notifications/')
    assert listed.status_code == 200
    rows = listed.data.get('results', listed.data)
    assert rows[0]['id'] == str(notification.id)
    read = auth_worker.post(f'/api/notifications/{notification.id}/mark_read/', {}, format='json')
    assert read.status_code == 200
    assert read.data['is_read'] is True
    deleted = auth_worker.delete(f'/api/notifications/{notification.id}/')
    assert deleted.status_code == 204
    state.refresh_from_db()
    assert state.deleted_at is not None


def test_push_device_registration_is_owned_by_current_user(auth_worker, worker_user, admin_user):
    first = auth_worker.post('/api/push-devices/', {'token': 'native-token-1', 'platform': 'android', 'device_name': 'Pixel'}, format='json')
    assert first.status_code == 201
    device = DeviceRegistration.objects.get(token='native-token-1')
    assert device.user_id == worker_user.id
    admin_client = auth(admin_user)
    moved = admin_client.post('/api/push-devices/', {'token': 'native-token-1', 'platform': 'android'}, format='json')
    assert moved.status_code == 201
    device.refresh_from_db()
    assert device.user_id == admin_user.id
    assert auth_worker.get('/api/push-devices/').data.get('results', []) == []


def test_workplace_channel_is_broadcast_only_for_workers_by_default(auth_worker, worker_user, manager_user):
    conversation = ensure_workplace_channel()
    assert conversation.channel.channel_type == ConversationChannel.ChannelType.WORKPLACE
    assert conversation.participants.filter(pk=worker_user.pk).exists()
    denied = auth_worker.post(f'/api/conversations/{conversation.id}/post_message/', {'body': 'Hallo Team'}, format='json')
    assert denied.status_code == 403
    manager_client = auth(manager_user)
    sent = manager_client.post(f'/api/conversations/{conversation.id}/post_message/', {'body': 'Schichtplan ist aktualisiert.'}, format='json')
    assert sent.status_code == 201
    assert sent.data['body'] == 'Schichtplan ist aktualisiert.'
    assert NotificationState.objects.filter(notification__user=worker_user, category='workchat').exists()


def test_manager_creates_direct_channel_worker_can_reply_and_delete_own_message(manager_user, worker_user):
    manager_client = auth(manager_user)
    created = manager_client.post('/api/conversations/', {'participants': [str(worker_user.id)]}, format='json')
    assert created.status_code == 201
    assert created.data['channel_type'] == 'direct'
    conversation_id = created.data['id']
    worker_client = auth(worker_user)
    reply = worker_client.post(f'/api/conversations/{conversation_id}/post_message/', {'body': 'Bin dabei.'}, format='json')
    assert reply.status_code == 201
    deleted = worker_client.delete(f"/api/workchat/messages/{reply.data['id']}/delete/")
    assert deleted.status_code == 204
    refreshed = worker_client.get(f'/api/conversations/{conversation_id}/')
    message = next(item for item in refreshed.data['messages'] if item['id'] == reply.data['id'])
    assert message['body'] == 'Nachricht gelöscht'
    assert message['deleted_at'] is not None


def test_scoped_manager_candidates_exclude_workers_outside_scope(manager_user, second_worker):
    allowed_user = second_worker.user
    outside_user = User.objects.create_user('outside@example.com', 'StrongPass123!', first_name='Outside', role=User.Role.WORKER)
    outside = WorkerProfile.objects.create(user=outside_user, employee_number='MA-OUT', employment_type='teilzeit', monthly_hours='40')
    role = AccessRole.objects.create(code='chat-supervisor-test', name='Chat Supervisor', permissions=['manager.access', 'workplace.view'])
    assignment = UserAccessAssignment.objects.create(user=manager_user, access_role=role, scope_mode='scoped')
    assignment.workers.add(second_worker)
    response = auth(manager_user).get('/api/communications/candidates/')
    assert response.status_code == 200
    ids = {row['id'] for row in response.data}
    assert str(allowed_user.id) in ids
    assert str(outside.user_id) not in ids


def test_publishing_open_shift_notifies_eligible_workers(worker_user, second_worker, company, location, position):
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=timezone.now() + timedelta(days=2),
        ends_at=timezone.now() + timedelta(days=2, hours=6),
        status=Shift.Status.DRAFT,
        required_count=1,
    )
    shift.status = Shift.Status.PUBLISHED
    shift.published_at = timezone.now()
    shift.save(update_fields=['status', 'published_at', 'updated_at'])
    notified_ids = set(NotificationState.objects.filter(category='open_shift').values_list('notification__user_id', flat=True))
    assert worker_user.id in notified_ids
    assert second_worker.user_id in notified_ids


def test_disabling_workchat_requires_confirmation_and_clears_history(auth_admin, admin_user, worker_user):
    conversation = ensure_workplace_channel()
    conversation.messages.create(sender=admin_user, body='Historie')
    denied = auth_admin.patch('/api/communications/settings/', {'workchat_enabled': False}, format='json')
    assert denied.status_code == 409
    assert Conversation.objects.filter(pk=conversation.pk).exists()
    confirmed = auth_admin.patch('/api/communications/settings/', {'workchat_enabled': False, 'confirm_delete_history': True}, format='json')
    assert confirmed.status_code == 200
    assert confirmed.data['workchat_enabled'] is False
    assert not Conversation.objects.filter(channel__isnull=False).exists()


def test_sms_delivery_respects_wiw_style_daily_cap(worker_user):
    notification = Notification.objects.create(user=worker_user, kind='workplace-sms-cap', title='Test', body='Text')
    now = timezone.now()
    for index in range(20):
        other = Notification.objects.create(user=worker_user, kind=f'sms-{index}', title='x')
        NotificationDelivery.objects.create(
            notification=other,
            channel=NotificationDelivery.Channel.SMS,
            status=NotificationDelivery.Status.SENT,
            sent_at=now,
        )
    status_value, provider, response, error = _send_sms(notification)
    assert status_value == 'skipped'
    assert provider == 'twilio'
    assert response['reason'] == 'daily-cap'
    assert response['limit'] == 20


def test_first_workchat_preference_created_from_delivery_uses_safe_defaults(worker_user):
    assert not NotificationPreference.objects.filter(user=worker_user, category='workchat').exists()
    pref = get_preference(worker_user, NotificationPreference.Category.WORKCHAT)
    assert pref.email_enabled is False
    assert pref.sms_enabled is False
