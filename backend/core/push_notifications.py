import base64
import json
import os
import time
from typing import Any

import httpx
import jwt
from celery import shared_task
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from .models import Notification
from .notification_settings import render_push_notification
from .push_models import PushDevice

FCM_SCOPE = 'https://www.googleapis.com/auth/firebase.messaging'
DEFAULT_BUNDLE_ID = 'de.aplussolution.workforce'
_FCM_CACHE: dict[str, Any] = {'token': '', 'expires_at': 0.0}
_APNS_CACHE: dict[str, Any] = {'token': '', 'expires_at': 0.0, 'key_id': '', 'team_id': ''}


def _multiline(value: str) -> str:
    return (value or '').replace('\\n', '\n').strip()


def _firebase_credentials() -> dict[str, Any]:
    raw = os.getenv('FIREBASE_CREDENTIALS_JSON', '').strip()
    if not raw:
        return {}
    if not raw.startswith('{'):
        try:
            raw = base64.b64decode(raw).decode('utf-8')
        except Exception:
            return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def firebase_project_id() -> str:
    configured = os.getenv('FIREBASE_PROJECT_ID', '').strip()
    return configured or str(_firebase_credentials().get('project_id') or '').strip()


def _apns_values() -> tuple[str, str, str, str, bool]:
    # APNs auth keys are capability-scoped. Do not reuse Sign in with Apple or
    # App Store Connect API keys here: they can be syntactically valid .p8 keys
    # while still being rejected by APNs.
    team_id = os.getenv('APNS_TEAM_ID', '').strip() or os.getenv('APPLE_TEAM_ID', '').strip()
    key_id = os.getenv('APNS_KEY_ID', '').strip()
    private_key = _multiline(os.getenv('APNS_PRIVATE_KEY', ''))
    bundle_id = os.getenv('APNS_BUNDLE_ID', '').strip() or DEFAULT_BUNDLE_ID
    sandbox = os.getenv('APNS_USE_SANDBOX', '0').strip().lower() in {'1', 'true', 'yes'}
    return team_id, key_id, private_key, bundle_id, sandbox


def push_provider_status() -> dict[str, bool]:
    firebase = _firebase_credentials()
    team_id, key_id, private_key, _, _ = _apns_values()
    return {
        'android': bool(firebase_project_id() and firebase.get('client_email') and firebase.get('private_key')),
        'ios': bool(team_id and key_id and private_key),
    }


def push_provider_configured() -> bool:
    status = push_provider_status()
    return status['android'] or status['ios']


def _fcm_access_token() -> str:
    now = time.time()
    if _FCM_CACHE['token'] and float(_FCM_CACHE['expires_at']) > now + 60:
        return str(_FCM_CACHE['token'])
    info = _firebase_credentials()
    if not info:
        raise RuntimeError('Firebase service account is not configured.')
    credentials = service_account.Credentials.from_service_account_info(info, scopes=[FCM_SCOPE])
    credentials.refresh(GoogleAuthRequest())
    expires = credentials.expiry.timestamp() if credentials.expiry else now + 3000
    _FCM_CACHE.update(token=credentials.token or '', expires_at=expires)
    if not credentials.token:
        raise RuntimeError('Firebase access token could not be created.')
    return credentials.token


def _apns_provider_token() -> str:
    team_id, key_id, private_key, _, _ = _apns_values()
    if not (team_id and key_id and private_key):
        raise RuntimeError('Dedicated APNs signing key is not configured.')
    now = time.time()
    if (
        _APNS_CACHE['token']
        and float(_APNS_CACHE['expires_at']) > now + 60
        and _APNS_CACHE['key_id'] == key_id
        and _APNS_CACHE['team_id'] == team_id
    ):
        return str(_APNS_CACHE['token'])
    token = jwt.encode(
        {'iss': team_id, 'iat': int(now)},
        private_key,
        algorithm='ES256',
        headers={'kid': key_id},
    )
    _APNS_CACHE.update(token=token, expires_at=now + 3000, key_id=key_id, team_id=team_id)
    return token


def _data_payload(notification: Notification) -> dict[str, str]:
    return {
        'notification_id': str(notification.id),
        'kind': str(notification.kind or 'general'),
        'action_url': str(notification.action_url or ''),
    }


def _send_android(
    device: PushDevice,
    notification: Notification,
    title: str,
    body: str,
) -> tuple[bool, str, bool]:
    project_id = firebase_project_id()
    if not project_id:
        return False, 'Firebase project is not configured.', False
    payload = {
        'message': {
            'token': device.token,
            'notification': {
                'title': title,
                'body': body,
            },
            'data': _data_payload(notification),
            'android': {
                'priority': 'high',
                'notification': {
                    'sound': 'default',
                    'channel_id': 'aplus_updates',
                },
            },
        },
    }
    try:
        response = httpx.post(
            f'https://fcm.googleapis.com/v1/projects/{project_id}/messages:send',
            headers={'Authorization': f'Bearer {_fcm_access_token()}'},
            json=payload,
            timeout=15.0,
        )
    except Exception as exc:
        return False, f'FCM transport: {exc}', False
    if 200 <= response.status_code < 300:
        return True, '', False
    text = response.text[:1000]
    invalid = response.status_code in {400, 404} and any(
        marker in text for marker in ('UNREGISTERED', 'registration-token-not-registered', 'INVALID_ARGUMENT')
    )
    return False, f'FCM {response.status_code}: {text}', invalid


def _send_ios(
    device: PushDevice,
    notification: Notification,
    title: str,
    body: str,
) -> tuple[bool, str, bool]:
    _, _, _, bundle_id, sandbox = _apns_values()
    host = 'https://api.sandbox.push.apple.com' if sandbox else 'https://api.push.apple.com'
    payload = {
        'aps': {
            'alert': {'title': title, 'body': body},
            'sound': 'default',
            'badge': 1,
        },
        **_data_payload(notification),
    }
    headers = {
        'authorization': f'bearer {_apns_provider_token()}',
        'apns-topic': bundle_id,
        'apns-push-type': 'alert',
        'apns-priority': '10',
    }
    try:
        with httpx.Client(http2=True, timeout=15.0) as client:
            response = client.post(f'{host}/3/device/{device.token}', headers=headers, json=payload)
    except Exception as exc:
        return False, f'APNs transport: {exc}', False
    if response.status_code == 200:
        return True, '', False
    try:
        reason = str(response.json().get('reason') or response.text[:500])
    except Exception:
        reason = response.text[:500]
    invalid = response.status_code == 410 or reason in {'BadDeviceToken', 'DeviceTokenNotForTopic', 'Unregistered'}
    return False, f'APNs {response.status_code}: {reason}', invalid


def deliver_notification(notification: Notification) -> dict[str, int]:
    result = {'sent': 0, 'failed': 0, 'deactivated': 0, 'skipped': 0}
    enabled, title, body, _rule_key = render_push_notification(notification)
    devices = PushDevice.objects.filter(user=notification.user, active=True).order_by('-last_seen_at')
    if not enabled:
        result['skipped'] = devices.count()
        return result

    providers = push_provider_status()
    for device in devices:
        if not providers.get(device.platform, False):
            result['skipped'] += 1
            continue
        if device.platform == PushDevice.Platform.ANDROID:
            ok, error, invalid = _send_android(device, notification, title, body)
        elif device.platform == PushDevice.Platform.IOS:
            ok, error, invalid = _send_ios(device, notification, title, body)
        else:
            result['skipped'] += 1
            continue
        if ok:
            result['sent'] += 1
            if device.last_error:
                device.last_error = ''
                device.save(update_fields=['last_error', 'updated_at'])
            continue
        result['failed'] += 1
        device.last_error = error[:2000]
        if invalid:
            device.active = False
            result['deactivated'] += 1
            device.save(update_fields=['last_error', 'active', 'updated_at'])
        else:
            device.save(update_fields=['last_error', 'updated_at'])
    return result


@shared_task
def send_notification_push(notification_id: str):
    notification = Notification.objects.select_related('user').filter(pk=notification_id).first()
    if not notification:
        return {'missing': 1}
    return deliver_notification(notification)
