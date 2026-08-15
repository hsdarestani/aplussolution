import base64
import csv
import hashlib
import hmac
import io
import ipaddress
import json
import secrets
import socket
import uuid
from datetime import timedelta
from urllib.parse import urlparse

import requests
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .integration_v7_models import (
    IntegrationApiKey,
    PayrollConnector,
    PayrollExportRun,
    WebhookDelivery,
    WebhookSubscription,
)
from .payroll_models import PayPeriod


API_KEY_SCOPES = {
    'workers.read',
    'shifts.read',
    'timesheets.read',
    'payroll.export',
    'webhooks.write',
}


def validate_outbound_url(url):
    parsed = urlparse(str(url or '').strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Outbound integration URLs must use HTTPS and may not contain embedded credentials.')
    host = parsed.hostname.lower().rstrip('.')
    if host in {'localhost', 'localhost.localdomain'} or host.endswith('.local') or host.endswith('.internal'):
        raise ValueError('Private or local integration hosts are not allowed.')
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise ValueError('Integration host could not be resolved.') from exc
    if not addresses:
        raise ValueError('Integration host could not be resolved.')
    for value in addresses:
        ip = ipaddress.ip_address(value)
        if not ip.is_global:
            raise ValueError('Integration host resolves to a non-public IP address.')
    return parsed.geturl()


def _fernet():
    digest = hashlib.sha256(settings.SECRET_KEY.encode('utf-8')).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value):
    if not value:
        return ''
    raw = json.dumps(value, separators=(',', ':'), sort_keys=True).encode('utf-8')
    return _fernet().encrypt(raw).decode('ascii')


def decrypt_secret(value):
    if not value:
        return {}
    return json.loads(_fernet().decrypt(value.encode('ascii')).decode('utf-8'))


def create_api_key(*, name, scopes, created_by, expires_at=None):
    scopes = sorted(set(scopes or []))
    unknown = set(scopes) - API_KEY_SCOPES
    if unknown:
        raise ValueError(f'Unknown API key scopes: {", ".join(sorted(unknown))}')
    prefix = secrets.token_hex(5)
    secret = secrets.token_urlsafe(32)
    token = f'awf_{prefix}_{secret}'
    row = IntegrationApiKey.objects.create(
        name=name,
        prefix=prefix,
        secret_hash=make_password(secret),
        scopes=scopes,
        created_by=created_by,
        expires_at=expires_at,
    )
    return row, token


def authenticate_api_key(request, required_scope=None):
    raw = request.headers.get('X-API-Key', '')
    if not raw:
        auth = request.headers.get('Authorization', '')
        if auth.lower().startswith('api-key '):
            raw = auth[8:].strip()
    if not raw.startswith('awf_'):
        return None
    try:
        _, prefix, secret = raw.split('_', 2)
    except ValueError:
        return None
    row = IntegrationApiKey.objects.filter(prefix=prefix).first()
    if not row or not row.usable or not check_password(secret, row.secret_hash):
        return None
    if required_scope and required_scope not in (row.scopes or []):
        return None
    IntegrationApiKey.objects.filter(pk=row.pk).update(last_used_at=timezone.now())
    return row


def rotate_webhook_secret(subscription):
    secret = secrets.token_urlsafe(36)
    subscription.secret_encrypted = encrypt_secret({'secret': secret})
    subscription.save(update_fields=['secret_encrypted', 'updated_at'])
    return secret


def _webhook_matches(subscription, event_type):
    configured = subscription.event_types or []
    return '*' in configured or event_type in configured


def emit_webhook_event(event_type, payload, event_id=None):
    event_id = event_id or uuid.uuid4()
    deliveries = []
    for subscription in WebhookSubscription.objects.filter(active=True):
        if not _webhook_matches(subscription, event_type):
            continue
        delivery, created = WebhookDelivery.objects.get_or_create(
            subscription=subscription,
            event_id=event_id,
            defaults={'event_type': event_type, 'payload': payload},
        )
        if created:
            deliveries.append(delivery)
    return deliveries


def sign_webhook(subscription, body, timestamp):
    secret = decrypt_secret(subscription.secret_encrypted).get('secret', '')
    signed = f'{timestamp}.'.encode('utf-8') + body
    return 'sha256=' + hmac.new(secret.encode('utf-8'), signed, hashlib.sha256).hexdigest()


def deliver_webhook(delivery):
    subscription = delivery.subscription
    now = timezone.now()
    if not subscription.active:
        delivery.status = WebhookDelivery.Status.DEAD
        delivery.last_error = 'Subscription disabled.'
        delivery.save(update_fields=['status', 'last_error', 'updated_at'])
        return delivery
    body = json.dumps(delivery.payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    timestamp = str(int(now.timestamp()))
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'APlusWorkforce-Webhooks/1.0',
        'X-APlus-Event': delivery.event_type,
        'X-APlus-Delivery': str(delivery.event_id),
        'X-APlus-Timestamp': timestamp,
        'X-APlus-Signature': sign_webhook(subscription, body, timestamp),
    }
    delivery.attempts += 1
    try:
        safe_url = validate_outbound_url(subscription.url)
        response = requests.post(safe_url, data=body, headers=headers, timeout=subscription.timeout_seconds)
        delivery.last_http_status = response.status_code
        if 200 <= response.status_code < 300:
            delivery.status = WebhookDelivery.Status.DELIVERED
            delivery.delivered_at = now
            delivery.last_error = ''
            subscription.last_success_at = now
            subscription.save(update_fields=['last_success_at', 'updated_at'])
        else:
            raise RuntimeError(f'HTTP {response.status_code}')
    except Exception as exc:
        delivery.last_error = str(exc)[:1000]
        subscription.last_failure_at = now
        subscription.save(update_fields=['last_failure_at', 'updated_at'])
        if delivery.attempts >= subscription.max_attempts:
            delivery.status = WebhookDelivery.Status.DEAD
        else:
            delivery.status = WebhookDelivery.Status.RETRY
            delay_minutes = min(60, 2 ** max(0, delivery.attempts - 1))
            delivery.next_attempt_at = now + timedelta(minutes=delay_minutes)
    delivery.save(update_fields=[
        'attempts', 'last_http_status', 'status', 'delivered_at', 'last_error', 'next_attempt_at', 'updated_at'
    ])
    return delivery


def due_webhook_deliveries(limit=100):
    return WebhookDelivery.objects.filter(
        status__in=[WebhookDelivery.Status.PENDING, WebhookDelivery.Status.RETRY],
        next_attempt_at__lte=timezone.now(),
    ).select_related('subscription').order_by('next_attempt_at')[:limit]


def pay_period_snapshot(pay_period):
    timesheets = pay_period.timesheets.select_related('worker__user').prefetch_related('entries').order_by('worker__employee_number')
    rows = []
    for sheet in timesheets:
        rows.append({
            'employee_number': sheet.worker.employee_number,
            'employee_name': sheet.worker.user.get_full_name() or sheet.worker.user.email,
            'status': sheet.status,
            'gross_minutes': sheet.gross_minutes,
            'paid_break_minutes': sheet.paid_break_minutes,
            'unpaid_break_minutes': sheet.unpaid_break_minutes,
            'net_minutes': sheet.net_minutes,
            'gross_estimate': str(sheet.gross_estimate),
            'entries': [
                {
                    'clock_in': item.clock_in.isoformat(),
                    'clock_out': item.clock_out.isoformat() if item.clock_out else None,
                    'net_minutes': item.net_minutes,
                    'hourly_rate': str(item.hourly_rate),
                    'amount_estimate': str(item.amount_estimate),
                }
                for item in sheet.entries.all()
            ],
        })
    return {
        'pay_period': {
            'id': str(pay_period.id),
            'name': pay_period.name,
            'starts_on': pay_period.starts_on.isoformat(),
            'ends_on': pay_period.ends_on.isoformat(),
            'status': pay_period.status,
            'currency': pay_period.currency,
        },
        'timesheets': rows,
    }


def _datev_csv(snapshot):
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Personalnummer', 'Name', 'Von', 'Bis', 'Netto_Minuten', 'Brutto_EUR'])
    period = snapshot['pay_period']
    for row in snapshot['timesheets']:
        writer.writerow([
            row['employee_number'], row['employee_name'], period['starts_on'], period['ends_on'],
            row['net_minutes'], row['gross_estimate'].replace('.', ','),
        ])
    return output.getvalue().encode('utf-8-sig'), 'text/csv', 'csv'


def export_payroll(connector, pay_period, created_by=None):
    if pay_period.status not in {PayPeriod.Status.CLOSED, PayPeriod.Status.LOCKED}:
        raise ValueError('Payroll exports require a closed or locked pay period.')
    snapshot = pay_period_snapshot(pay_period)
    run, _ = PayrollExportRun.objects.get_or_create(
        connector=connector,
        pay_period=pay_period,
        defaults={'created_by': created_by},
    )
    run.status = PayrollExportRun.Status.RUNNING
    run.error = ''
    run.save(update_fields=['status', 'error', 'updated_at'])
    try:
        if connector.provider == PayrollConnector.Provider.DATEV_CSV:
            content, content_type, extension = _datev_csv(snapshot)
            result = {
                'mode': 'download',
                'content_b64': base64.b64encode(content).decode('ascii'),
                'content_type': content_type,
                'filename': f'payroll-{pay_period.starts_on}-{pay_period.ends_on}.{extension}',
            }
        elif connector.provider == PayrollConnector.Provider.GENERIC_JSON:
            url = connector.configuration.get('url')
            if not url:
                raise ValueError('Generic JSON connector requires configuration.url.')
            safe_url = validate_outbound_url(url)
            credentials = decrypt_secret(connector.credentials_encrypted)
            headers = {'Content-Type': 'application/json'}
            if credentials.get('bearer_token'):
                headers['Authorization'] = f"Bearer {credentials['bearer_token']}"
            response = requests.post(safe_url, json=snapshot, headers=headers, timeout=int(connector.configuration.get('timeout_seconds', 20)))
            if not 200 <= response.status_code < 300:
                raise RuntimeError(f'Payroll provider returned HTTP {response.status_code}')
            result = {'mode': 'remote', 'http_status': response.status_code}
        else:
            raise ValueError('Unsupported payroll connector provider.')
        canonical = json.dumps(snapshot, separators=(',', ':'), sort_keys=True).encode('utf-8')
        run.status = PayrollExportRun.Status.SUCCESS
        run.record_count = len(snapshot['timesheets'])
        run.checksum = hashlib.sha256(canonical).hexdigest()
        run.result = {k: v for k, v in result.items() if k != 'content_b64'}
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'record_count', 'checksum', 'result', 'completed_at', 'updated_at'])
        connector.last_export_at = timezone.now()
        connector.save(update_fields=['last_export_at', 'updated_at'])
        return run, result
    except Exception as exc:
        run.status = PayrollExportRun.Status.FAILED
        run.error = str(exc)[:2000]
        run.completed_at = timezone.now()
        run.save(update_fields=['status', 'error', 'completed_at', 'updated_at'])
        raise
