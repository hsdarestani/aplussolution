import json
import logging
from datetime import datetime
from urllib.parse import urlencode

import requests
import jwt
import httpx
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from .communications_models import (
    CommunicationSettings,
    ConversationChannel,
    ConversationMembership,
    DeviceRegistration,
    NotificationDelivery,
    NotificationPreference,
    NotificationState,
)
from .models import Conversation, Message, Notification, User
from .workplace_access import visible_workers


logger = logging.getLogger(__name__)


CATEGORY_PREFIXES = (
    ('shift-24h-', NotificationPreference.Category.SHIFT_REMINDER),
    ('shift-reminder', NotificationPreference.Category.SHIFT_REMINDER),
    ('schedule-', NotificationPreference.Category.SCHEDULE),
    ('shift-', NotificationPreference.Category.SCHEDULE),
    ('open-shift', NotificationPreference.Category.OPEN_SHIFT),
    ('swap-', NotificationPreference.Category.SWAP_DROP),
    ('time-off', NotificationPreference.Category.TIME_OFF),
    ('absence', NotificationPreference.Category.ABSENCE),
    ('coverage-', NotificationPreference.Category.ABSENCE),
    ('attendance', NotificationPreference.Category.CLOCK),
    ('clock-', NotificationPreference.Category.CLOCK),
    ('overtime', NotificationPreference.Category.OVERTIME),
    ('payroll', NotificationPreference.Category.PAYROLL),
    ('timesheet', NotificationPreference.Category.PAYROLL),
    ('report', NotificationPreference.Category.REPORTS),
    ('workchat', NotificationPreference.Category.WORKCHAT),
    ('message-', NotificationPreference.Category.WORKCHAT),
    ('availability', NotificationPreference.Category.AVAILABILITY),
    ('user-', NotificationPreference.Category.NEW_USER),
    ('portal-', NotificationPreference.Category.NEW_USER),
    ('contract-', NotificationPreference.Category.WORKPLACE),
)


def infer_category(kind):
    value = str(kind or '').lower()
    for prefix, category in CATEGORY_PREFIXES:
        if value.startswith(prefix):
            return category
    return NotificationPreference.Category.WORKPLACE


def _preference_defaults(category):
    if category == NotificationPreference.Category.WORKCHAT:
        return {'email_enabled': False, 'sms_enabled': False}
    if category == NotificationPreference.Category.REPORTS:
        return {'push_enabled': False}
    return {}


def ensure_preferences(user):
    existing = {
        item.category: item
        for item in NotificationPreference.objects.filter(user=user)
    }
    result = []
    for category, _label in NotificationPreference.Category.choices:
        if category in existing:
            result.append(existing[category])
            continue
        pref = NotificationPreference.objects.create(user=user, category=category, **_preference_defaults(category))
        result.append(pref)
    return result


def ensure_notification_state(notification, *, category=None, priority=None, data=None, dedupe_key=''):
    category = category or infer_category(notification.kind)
    defaults = {
        'category': category,
        'data': data or {},
        'dedupe_key': dedupe_key or notification.kind or '',
    }
    if priority:
        defaults['priority'] = priority
    state, created = NotificationState.objects.get_or_create(notification=notification, defaults=defaults)
    if not created:
        changed = []
        if category and state.category != category:
            state.category = category
            changed.append('category')
        if data and state.data != data:
            state.data = data
            changed.append('data')
        if priority and state.priority != priority:
            state.priority = priority
            changed.append('priority')
        if dedupe_key and state.dedupe_key != dedupe_key:
            state.dedupe_key = dedupe_key
            changed.append('dedupe_key')
        if changed:
            state.save(update_fields=changed + ['updated_at'])
    return state


def notify(user, *, category, title, body='', action_url='', kind='', priority=NotificationState.Priority.NORMAL, data=None, dedupe_key=''):
    if not user or not user.is_active:
        return None
    pref = get_preference(user, category)
    if not pref.in_app_enabled and not pref.push_enabled and not pref.email_enabled and not pref.sms_enabled:
        return None
    dedupe = str(dedupe_key or kind or '').strip()
    if dedupe:
        existing = NotificationState.objects.filter(
            notification__user=user,
            dedupe_key=dedupe,
            deleted_at__isnull=True,
        ).select_related('notification').first()
        if existing:
            return existing.notification
    notification = Notification.objects.create(
        user=user,
        title=title,
        body=body,
        kind=kind or f'{category}-{timezone.now().timestamp()}',
        action_url=action_url,
    )
    ensure_notification_state(
        notification,
        category=category,
        priority=priority,
        data=data or {},
        dedupe_key=dedupe,
    )
    enqueue_notification(notification)
    return notification


def get_preference(user, category):
    pref, _ = NotificationPreference.objects.get_or_create(user=user, category=category, defaults=_preference_defaults(category))
    return pref


def in_dnd(pref, now=None):
    if not pref.dnd_start or not pref.dnd_end:
        return False
    local = timezone.localtime(now or timezone.now()).time().replace(tzinfo=None)
    start, end = pref.dnd_start, pref.dnd_end
    if start == end:
        return False
    if start < end:
        return start <= local < end
    return local >= start or local < end


def enqueue_notification(notification):
    state = ensure_notification_state(notification)
    if state.delivery_enqueued_at:
        return
    state.delivery_enqueued_at = timezone.now()
    state.save(update_fields=['delivery_enqueued_at', 'updated_at'])
    try:
        from .communications_tasks import dispatch_notification
        transaction.on_commit(lambda: _safe_delay(dispatch_notification, str(notification.id)))
    except Exception:
        logger.exception('Unable to enqueue notification %s', notification.pk)


def _safe_delay(task, *args):
    try:
        task.delay(*args)
    except Exception:
        logger.warning('Celery enqueue failed for %s', getattr(task, 'name', task), exc_info=True)


def _fcm_credentials():
    project_id = getattr(settings, 'FCM_PROJECT_ID', '')
    raw = getattr(settings, 'FCM_SERVICE_ACCOUNT_JSON', '')
    path = getattr(settings, 'FCM_SERVICE_ACCOUNT_FILE', '')
    if not project_id:
        return None, None
    try:
        if raw:
            info = json.loads(raw)
            credentials = service_account.Credentials.from_service_account_info(
                info, scopes=['https://www.googleapis.com/auth/firebase.messaging']
            )
        elif path:
            credentials = service_account.Credentials.from_service_account_file(
                path, scopes=['https://www.googleapis.com/auth/firebase.messaging']
            )
        else:
            return None, None
        credentials.refresh(GoogleAuthRequest())
        return project_id, credentials.token
    except Exception:
        logger.exception('Could not load Firebase credentials')
        return None, None


def _apns_token():
    key_id = getattr(settings, 'APNS_KEY_ID', '')
    team_id = getattr(settings, 'APNS_TEAM_ID', '')
    private_key = getattr(settings, 'APNS_PRIVATE_KEY', '')
    if not key_id or not team_id or not private_key:
        return None
    now = int(timezone.now().timestamp())
    return jwt.encode(
        {'iss': team_id, 'iat': now},
        private_key,
        algorithm='ES256',
        headers={'kid': key_id},
    )


def _send_apns_device(device, notification, state):
    bundle_id = getattr(settings, 'APNS_BUNDLE_ID', '')
    token = _apns_token()
    if not bundle_id or not token:
        return False, {'reason': 'apns-not-configured'}
    host = 'https://api.sandbox.push.apple.com' if getattr(settings, 'APNS_USE_SANDBOX', False) else 'https://api.push.apple.com'
    payload = {
        'aps': {
            'alert': {'title': notification.title, 'body': notification.body or ''},
            'sound': 'default',
            'badge': 1,
        },
        'notification_id': str(notification.id),
        'category': state.category,
        'action_url': notification.action_url or '',
        **{str(k): v for k, v in (state.data or {}).items() if v is not None},
    }
    headers = {
        'authorization': f'bearer {token}',
        'apns-topic': bundle_id,
        'apns-push-type': 'alert',
        'apns-priority': '10' if state.priority in {'high', 'urgent'} else '5',
    }
    try:
        with httpx.Client(http2=True, timeout=12) as client:
            response = client.post(f'{host}/3/device/{device.token}', headers=headers, json=payload)
        body = response.json() if response.content else {}
        if 200 <= response.status_code < 300:
            return True, {'status': response.status_code, 'body': body}
        if response.status_code in {400, 410} and body.get('reason') in {'BadDeviceToken', 'Unregistered', 'DeviceTokenNotForTopic'}:
            device.active = False
            device.save(update_fields=['active', 'updated_at'])
        return False, {'status': response.status_code, 'body': body}
    except Exception as exc:
        return False, {'error': str(exc)}


def _send_fcm_device(device, notification, state, project_id, access_token):
    endpoint = f'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    payload = {
        'message': {
            'token': device.token,
            'notification': {'title': notification.title, 'body': notification.body or ''},
            'data': {
                'notification_id': str(notification.id),
                'category': state.category,
                'action_url': notification.action_url or '',
                **{str(k): str(v) for k, v in (state.data or {}).items() if v is not None},
            },
            'android': {'priority': 'high' if state.priority in {'high', 'urgent'} else 'normal'},
        }
    }
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=12)
        body = response.json() if response.headers.get('content-type', '').startswith('application/json') else {'text': response.text[:500]}
        if response.ok:
            return True, body
        if response.status_code in {400, 404} and ('UNREGISTERED' in response.text or 'registration-token-not-registered' in response.text):
            device.active = False
            device.save(update_fields=['active', 'updated_at'])
        return False, {'status': response.status_code, 'body': body}
    except requests.RequestException as exc:
        return False, {'error': str(exc)}


def _send_push(notification, state):
    devices = list(DeviceRegistration.objects.filter(user=notification.user, active=True))
    if not devices:
        return 'skipped', 'native', {'reason': 'no-active-device'}, ''
    android_devices = [item for item in devices if item.platform == DeviceRegistration.Platform.ANDROID]
    project_id, access_token = _fcm_credentials() if android_devices else (None, None)
    sent = []
    errors = []
    for device in devices:
        if device.platform == DeviceRegistration.Platform.IOS:
            ok, response = _send_apns_device(device, notification, state)
            provider = 'apns'
        elif device.platform == DeviceRegistration.Platform.ANDROID:
            if not project_id or not access_token:
                ok, response = False, {'reason': 'fcm-not-configured'}
            else:
                ok, response = _send_fcm_device(device, notification, state, project_id, access_token)
            provider = 'fcm'
        else:
            ok, response, provider = False, {'reason': 'web-push-not-configured'}, 'web'
        row = {'device': str(device.id), 'platform': device.platform, 'provider': provider, 'response': response}
        (sent if ok else errors).append(row)
    if sent:
        return 'sent', 'native', {'sent': sent, 'errors': errors}, ''
    configured = [item for item in errors if item['response'].get('reason') not in {'fcm-not-configured', 'apns-not-configured', 'web-push-not-configured'}]
    if not configured:
        return 'skipped', 'native', {'errors': errors}, 'No native push provider configured.'
    return 'failed', 'native', {'errors': errors}, 'Push delivery failed for all devices.'


def _send_email(notification):
    if not notification.user.email:
        return 'skipped', 'smtp', {'reason': 'missing-email'}, ''
    try:
        send_mail(
            notification.title,
            notification.body or notification.title,
            settings.DEFAULT_FROM_EMAIL,
            [notification.user.email],
            fail_silently=False,
        )
        return 'sent', 'smtp', {}, ''
    except Exception as exc:
        return 'failed', 'smtp', {}, str(exc)


def _send_sms(notification):
    today = timezone.localdate()
    sent_today = NotificationDelivery.objects.filter(
        notification__user=notification.user, channel=NotificationDelivery.Channel.SMS,
        status=NotificationDelivery.Status.SENT, sent_at__date=today,
    ).count()
    if sent_today >= 20:
        return 'skipped', 'twilio', {'reason': 'daily-cap', 'limit': 20}, ''
    cfg = CommunicationSettings.load()
    if not cfg.sms_fallback_enabled:
        return 'skipped', 'twilio', {'reason': 'sms-disabled'}, ''
    user = notification.user
    if not user.phone:
        return 'skipped', 'twilio', {'reason': 'missing-phone'}, ''
    sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '')
    token = getattr(settings, 'TWILIO_AUTH_TOKEN', '')
    sender = getattr(settings, 'TWILIO_FROM_NUMBER', '')
    if not sid or not token or not sender:
        return 'skipped', 'twilio', {'reason': 'twilio-not-configured'}, ''
    try:
        response = requests.post(
            f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
            auth=(sid, token),
            data={
                'From': sender,
                'To': user.phone,
                'Body': f'{notification.title}\n{notification.body}'.strip()[:1500],
            },
            timeout=12,
        )
        payload = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
        if response.ok:
            return 'sent', 'twilio', payload, ''
        return 'failed', 'twilio', payload, response.text[:500]
    except requests.RequestException as exc:
        return 'failed', 'twilio', {}, str(exc)


def dispatch_notification_now(notification):
    state = ensure_notification_state(notification)
    pref = get_preference(notification.user, state.category)
    if in_dnd(pref) and state.priority != NotificationState.Priority.URGENT:
        return {'deferred': True}

    channel_enabled = {
        NotificationDelivery.Channel.PUSH: pref.push_enabled,
        NotificationDelivery.Channel.EMAIL: pref.email_enabled,
        NotificationDelivery.Channel.SMS: pref.sms_enabled,
    }
    results = {}
    for channel, enabled in channel_enabled.items():
        delivery, _ = NotificationDelivery.objects.get_or_create(notification=notification, channel=channel)
        if delivery.status == NotificationDelivery.Status.SENT:
            results[channel] = delivery.status
            continue
        if not enabled:
            delivery.status = NotificationDelivery.Status.SKIPPED
            delivery.provider = ''
            delivery.error = 'Disabled by user preference.'
            delivery.attempts += 1
            delivery.save(update_fields=['status', 'provider', 'error', 'attempts', 'updated_at'])
            results[channel] = delivery.status
            continue
        if channel == NotificationDelivery.Channel.PUSH:
            status_value, provider, response, error = _send_push(notification, state)
        elif channel == NotificationDelivery.Channel.EMAIL:
            status_value, provider, response, error = _send_email(notification)
        else:
            status_value, provider, response, error = _send_sms(notification)
        delivery.status = status_value
        delivery.provider = provider
        delivery.provider_response = response
        delivery.error = error
        delivery.attempts += 1
        if status_value == NotificationDelivery.Status.SENT:
            delivery.sent_at = timezone.now()
        delivery.save(update_fields=['status', 'provider', 'provider_response', 'error', 'attempts', 'sent_at', 'updated_at'])
        results[channel] = status_value
    return results


def ensure_workplace_channel():
    channel = ConversationChannel.objects.filter(
        channel_type=ConversationChannel.ChannelType.WORKPLACE,
        active=True,
    ).select_related('conversation').first()
    if channel:
        _sync_workplace_members(channel.conversation)
        return channel.conversation
    conversation = Conversation.objects.create(title=getattr(settings, 'COMPANY_NAME', 'Betrieb'), is_announcement=True)
    channel = ConversationChannel.objects.create(
        conversation=conversation,
        channel_type=ConversationChannel.ChannelType.WORKPLACE,
        active=True,
        pinned=True,
    )
    _sync_workplace_members(conversation)
    return conversation


def _sync_workplace_members(conversation):
    users = User.objects.filter(is_active=True).exclude(role=User.Role.CLIENT)
    for user in users:
        conversation.participants.add(user)
        membership, _ = ConversationMembership.objects.get_or_create(conversation=conversation, user=user)
        if membership.left_at:
            membership.left_at = None
            membership.save(update_fields=['left_at', 'updated_at'])
    stale = ConversationMembership.objects.filter(conversation=conversation).exclude(user__in=users)
    stale.update(left_at=timezone.now())


def active_members(conversation):
    return User.objects.filter(
        channel_memberships__conversation=conversation,
        channel_memberships__left_at__isnull=True,
        is_active=True,
    ).distinct()


def is_active_member(conversation, user):
    return ConversationMembership.objects.filter(
        conversation=conversation,
        user=user,
        left_at__isnull=True,
    ).exists()


def can_post(conversation, user):
    cfg = CommunicationSettings.load()
    if not cfg.workchat_enabled or not is_active_member(conversation, user):
        return False
    channel = getattr(conversation, 'channel', None)
    if channel and channel.channel_type == ConversationChannel.ChannelType.WORKPLACE:
        if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return True
        return cfg.employees_can_post_workplace
    return True


def can_manage_channel(conversation, user):
    if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        return is_active_member(conversation, user) or user.role == User.Role.ADMIN
    membership = ConversationMembership.objects.filter(
        conversation=conversation, user=user, left_at__isnull=True
    ).first()
    return bool(membership and membership.role == ConversationMembership.Role.OWNER)


def candidate_users(user):
    qs = User.objects.filter(is_active=True).exclude(pk=user.pk).exclude(role=User.Role.CLIENT)
    if user.role == User.Role.ADMIN:
        return qs
    if user.role == User.Role.MANAGER:
        worker_user_ids = visible_workers(user).values_list('user_id', flat=True)
        return qs.filter(
            models_Q_manager_or_worker(worker_user_ids)
        ).distinct()
    if user.role == User.Role.WORKER:
        return qs.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER, User.Role.WORKER])
    return User.objects.none()


def models_Q_manager_or_worker(worker_user_ids):
    from django.db.models import Q
    return Q(role__in=[User.Role.ADMIN, User.Role.MANAGER]) | Q(id__in=worker_user_ids)


def create_channel(created_by, participant_ids, title=''):
    cfg = CommunicationSettings.load()
    if not cfg.workchat_enabled:
        raise ValueError('WorkChat ist deaktiviert.')
    if not cfg.users_can_create_channels and created_by.role not in {User.Role.ADMIN, User.Role.MANAGER}:
        raise PermissionError('Zusätzliche Kanäle sind deaktiviert.')
    ids = {str(item) for item in participant_ids if item}
    if not ids:
        raise ValueError('Mindestens ein Teilnehmer ist erforderlich.')
    allowed = candidate_users(created_by).filter(pk__in=ids)
    participants = list(allowed)
    if len(participants) != len(ids):
        raise PermissionError('Mindestens ein Benutzer liegt außerhalb deines Kommunikationsbereichs.')
    channel_type = ConversationChannel.ChannelType.DIRECT if len(participants) == 1 else ConversationChannel.ChannelType.GROUP
    all_users = [created_by, *participants]
    if channel_type == ConversationChannel.ChannelType.DIRECT:
        existing = ConversationChannel.objects.filter(
            channel_type=channel_type,
            active=True,
            conversation__participants=created_by,
        )
        for item in existing.select_related('conversation'):
            member_ids = set(active_members(item.conversation).values_list('id', flat=True))
            if member_ids == {u.id for u in all_users}:
                return item.conversation
    conversation = Conversation.objects.create(
        title=str(title or '').strip(),
        is_announcement=False,
    )
    conversation.participants.add(*all_users)
    ConversationChannel.objects.create(
        conversation=conversation,
        channel_type=channel_type,
        created_by=created_by,
    )
    for user in all_users:
        ConversationMembership.objects.create(
            conversation=conversation,
            user=user,
            role=ConversationMembership.Role.OWNER if user == created_by else ConversationMembership.Role.MEMBER,
        )
    return conversation


def post_message(conversation, sender, body='', attachment=None):
    if not can_post(conversation, sender):
        raise PermissionError('Du darfst in diesem Kanal nicht schreiben.')
    if not body and not attachment:
        raise ValueError('Nachricht oder Bild ist erforderlich.')
    cfg = CommunicationSettings.load()
    if attachment and not cfg.images_enabled:
        raise ValueError('Bilder sind in WorkChat deaktiviert.')
    if attachment:
        content_type = getattr(attachment, 'content_type', '') or ''
        if content_type not in {'image/png', 'image/jpeg', 'image/gif', 'image/webp'}:
            raise ValueError('Nur PNG, JPEG, GIF oder WebP Bilder sind erlaubt.')
        if getattr(attachment, 'size', 0) > 12 * 1024 * 1024:
            raise ValueError('Bilder dürfen maximal 12 MB groß sein.')
    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        body=str(body or '').strip(),
        attachment=attachment,
    )
    message.read_by.add(sender)
    now = timezone.now()
    ConversationMembership.objects.filter(conversation=conversation, user=sender).update(last_read_at=now)
    for recipient in active_members(conversation).exclude(pk=sender.pk):
        membership = ConversationMembership.objects.filter(conversation=conversation, user=recipient).first()
        if membership and (membership.muted or not membership.notifications_enabled):
            continue
        notify(
            recipient,
            category=NotificationPreference.Category.WORKCHAT,
            kind=f'workchat-{message.id}',
            title=sender.get_full_name() or sender.email,
            body=message.body or 'Bild',
            action_url=f'/messages?channel={conversation.id}',
            data={'conversation_id': str(conversation.id), 'message_id': str(message.id)},
            dedupe_key=f'workchat-{message.id}-{recipient.id}',
        )
    return message
