import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone

import redis
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction

from .models import WorkerProfile


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'
PASSWORD_RESET_BATCH_KEY = 'security:active-worker-password-reset:v1'
PASSWORD_RESET_BATCH_TTL_SECONDS = 6 * 60 * 60
PASSWORD_UPPER = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
PASSWORD_LOWER = 'abcdefghijkmnopqrstuvwxyz'
PASSWORD_DIGITS = '23456789'
PASSWORD_ALPHABET = PASSWORD_UPPER + PASSWORD_LOWER + PASSWORD_DIGITS


def generated_worker_password(length=10):
    """Generate a typo-resistant 10-char password with mixed character classes."""
    if length < 10:
        raise ValueError('Worker passwords must be at least 10 characters long.')
    chars = [
        secrets.choice(PASSWORD_UPPER),
        secrets.choice(PASSWORD_LOWER),
        secrets.choice(PASSWORD_DIGITS),
        secrets.choice(PASSWORD_DIGITS),
    ]
    chars.extend(secrets.choice(PASSWORD_ALPHABET) for _ in range(length - len(chars)))
    secrets.SystemRandom().shuffle(chars)
    return ''.join(chars)


def active_real_workers():
    return (
        WorkerProfile.objects.select_related('user')
        .filter(active=True, user__is_active=True)
        .exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
        .order_by('user__last_name', 'user__first_name', 'user__email')
    )


def reset_active_worker_passwords():
    credentials = []
    workers = list(active_real_workers())
    with transaction.atomic():
        for worker in workers:
            password = generated_worker_password()
            worker.user.set_password(password)
            worker.user.save(update_fields=['password'])
            credentials.append({
                'name': worker.user.get_full_name().strip() or worker.employee_number or 'Mitarbeiter',
                'email': worker.user.email,
                'username': worker.user.email,
                'password': password,
            })
    return credentials


def _redis_client():
    return redis.Redis.from_url(settings.CELERY_BROKER_URL, decode_responses=False)


def _fernet():
    material = f'{settings.SECRET_KEY}:active-worker-password-reset:v1'.encode('utf-8')
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def store_reset_batch(credentials):
    payload = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'expires_in_seconds': PASSWORD_RESET_BATCH_TTL_SECONDS,
        'count': len(credentials),
        'credentials': credentials,
    }
    encrypted = _fernet().encrypt(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    _redis_client().setex(PASSWORD_RESET_BATCH_KEY, PASSWORD_RESET_BATCH_TTL_SECONDS, encrypted)
    return {'count': len(credentials), 'created_at': payload['created_at']}


def read_reset_batch():
    encrypted = _redis_client().get(PASSWORD_RESET_BATCH_KEY)
    if not encrypted:
        return None
    try:
        payload = json.loads(_fernet().decrypt(encrypted).decode('utf-8'))
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return None
    ttl = _redis_client().ttl(PASSWORD_RESET_BATCH_KEY)
    payload['ttl_seconds'] = max(0, int(ttl or 0))
    return payload


def clear_reset_batch():
    return bool(_redis_client().delete(PASSWORD_RESET_BATCH_KEY))
