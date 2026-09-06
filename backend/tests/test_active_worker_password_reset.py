import re

import pytest
from rest_framework.test import APIClient

from core import searchable_views
from core.models import AuditLog, User, WorkerProfile


pytestmark = pytest.mark.django_db


def _worker(email, number, *, active=True, user_active=True):
    user = User.objects.create_user(
        email,
        'OldPass123!',
        first_name=number,
        role=User.Role.WORKER,
        is_active=user_active,
        is_onboarded=True,
    )
    return WorkerProfile.objects.create(user=user, employee_number=number, active=active)


def test_admin_resets_only_active_real_workers(auth_admin, worker_user, monkeypatch):
    inactive = _worker('inactive@example.com', 'MA-INACTIVE', active=False)
    disabled = _worker('disabled@example.com', 'MA-DISABLED', user_active=False)
    synthetic = _worker('wiw-999@sync.invalid', 'WIW-999')

    captured = {}

    def fake_store(rows):
        captured['rows'] = rows
        return {'count': len(rows), 'created_at': '2026-09-06T00:00:00+00:00'}

    monkeypatch.setattr(searchable_views, 'store_reset_batch', fake_store)

    response = auth_admin.post(
        '/api/workers/reset-active-passwords/',
        {'confirm': 'RESET_ACTIVE_WORKER_PASSWORDS'},
        format='json',
    )

    assert response.status_code == 200
    assert 'no-store' in response['Cache-Control']
    assert response.data['count'] == 1
    assert len(captured['rows']) == 1

    credential = response.data['credentials'][0]
    assert credential['username'] == worker_user.email
    assert credential['email'] == worker_user.email
    password = credential['password']
    assert len(password) == 10
    assert re.search(r'[A-Z]', password)
    assert re.search(r'[a-z]', password)
    assert len(re.findall(r'\d', password)) >= 2

    worker_user.refresh_from_db()
    assert not worker_user.check_password('StrongPass123!')
    assert worker_user.check_password(password)

    inactive.user.refresh_from_db()
    disabled.user.refresh_from_db()
    synthetic.user.refresh_from_db()
    assert inactive.user.check_password('OldPass123!')
    assert disabled.user.check_password('OldPass123!')
    assert synthetic.user.check_password('OldPass123!')

    audit = AuditLog.objects.filter(action='worker.bulk_password_reset').latest('created_at')
    assert audit.metadata == {'count': 1}
    assert password not in str(audit.metadata)


def test_bulk_reset_requires_explicit_confirmation(auth_admin, worker_user, monkeypatch):
    called = False

    def fake_reset():
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(searchable_views, 'reset_active_worker_passwords', fake_reset)
    response = auth_admin.post('/api/workers/reset-active-passwords/', {}, format='json')
    assert response.status_code == 400
    assert called is False


def test_manager_cannot_bulk_reset(manager_user):
    client = APIClient()
    client.force_authenticate(manager_user)
    response = client.post(
        '/api/workers/reset-active-passwords/',
        {'confirm': 'RESET_ACTIVE_WORKER_PASSWORDS'},
        format='json',
    )
    assert response.status_code == 403


def test_admin_can_reveal_only_encrypted_temporary_batch(auth_admin, monkeypatch):
    payload = {
        'count': 1,
        'credentials': [{'name': 'Test', 'username': 'test@example.com', 'email': 'test@example.com', 'password': 'A2b3c4D5e6'}],
        'ttl_seconds': 1200,
    }
    monkeypatch.setattr(searchable_views, 'read_reset_batch', lambda: payload)

    response = auth_admin.post(
        '/api/workers/active-password-batch/',
        {'confirm': 'SHOW_ACTIVE_WORKER_PASSWORDS'},
        format='json',
    )
    assert response.status_code == 200
    assert response.data == payload
    assert 'no-store' in response['Cache-Control']
