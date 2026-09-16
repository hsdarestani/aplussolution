from __future__ import annotations

import httpx

from .push_models import PushDevice
from .push_notifications import _apns_provider_token, _apns_values, push_provider_status


def clear_ios_badge(user) -> dict[str, int]:
    """Best-effort reset of the native iOS app icon badge for a user.

    APNs badge state lives on the device and is independent from the database
    read state. Marking Notification rows as read therefore does not clear a
    badge that was previously sent by APNs; an explicit badge=0 push is needed.
    """
    result = {'sent': 0, 'failed': 0, 'deactivated': 0, 'skipped': 0}
    devices = list(
        PushDevice.objects.filter(
            user=user,
            active=True,
            platform=PushDevice.Platform.IOS,
        ).order_by('-last_seen_at')
    )
    if not devices:
        return result
    if not push_provider_status().get('ios', False):
        result['skipped'] = len(devices)
        return result

    _, _, _, bundle_id, sandbox = _apns_values()
    host = 'https://api.sandbox.push.apple.com' if sandbox else 'https://api.push.apple.com'
    try:
        provider_token = _apns_provider_token()
    except Exception:
        result['failed'] = len(devices)
        return result

    headers = {
        'authorization': f'bearer {provider_token}',
        'apns-topic': bundle_id,
        'apns-push-type': 'alert',
        'apns-priority': '10',
    }
    payload = {'aps': {'badge': 0}}

    try:
        client = httpx.Client(http2=True, timeout=5.0)
    except Exception:
        result['failed'] = len(devices)
        return result

    with client:
        for device in devices:
            invalid = False
            error = ''
            try:
                response = client.post(f'{host}/3/device/{device.token}', headers=headers, json=payload)
                if response.status_code == 200:
                    result['sent'] += 1
                    if device.last_error:
                        device.last_error = ''
                        device.save(update_fields=['last_error', 'updated_at'])
                    continue
                try:
                    reason = str(response.json().get('reason') or response.text[:500])
                except Exception:
                    reason = response.text[:500]
                invalid = response.status_code == 410 or reason in {
                    'BadDeviceToken',
                    'DeviceTokenNotForTopic',
                    'Unregistered',
                }
                error = f'APNs badge reset {response.status_code}: {reason}'
            except Exception as exc:
                error = f'APNs badge reset transport: {exc}'

            result['failed'] += 1
            device.last_error = error[:2000]
            if invalid:
                device.active = False
                result['deactivated'] += 1
                device.save(update_fields=['last_error', 'active', 'updated_at'])
            else:
                device.save(update_fields=['last_error', 'updated_at'])

    return result
