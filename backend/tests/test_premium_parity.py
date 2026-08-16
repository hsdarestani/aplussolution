from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Shift
from core.premium_models import SchedulingPolicy
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_premium_policy_and_auto_schedule(auth_admin, company, location, position, worker_user, second_worker):
    policy = auth_admin.get('/api/premium/scheduling-policy/')
    assert policy.status_code == 200
    assert policy.data['auto_schedule_enabled'] is True

    start = timezone.now() + timedelta(days=2)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        status=Shift.Status.PUBLISHED,
        required_count=1,
    )
    assert shift.slots.filter(status=ShiftSlot.Status.OPEN).count() == 1

    response = auth_admin.post('/api/premium/auto-schedule/', {
        'start': (start - timedelta(hours=1)).isoformat(),
        'end': (start + timedelta(days=1)).isoformat(),
        'apply': True,
    }, format='json')
    assert response.status_code == 200
    assert response.data['assigned'] == 1
    slot = shift.slots.get()
    slot.refresh_from_db()
    assert slot.status == ShiftSlot.Status.CLAIMED
    assert slot.worker_id in {worker_user.worker_profile.id, second_worker.id}


@pytest.mark.django_db
def test_pickup_approval_mode(auth_admin, auth_worker, company, location, position, worker_user):
    policy = SchedulingPolicy.objects.create(name='Approval', pickup_approval_required=True)
    start = timezone.now() + timedelta(days=3)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=5),
        status=Shift.Status.PUBLISHED,
    )

    response = auth_worker.post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert response.status_code == 202
    assert response.data['pending_approval'] is True
    request_id = response.data['request_id']
    assert not shift.slots.filter(worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED).exists()

    pending = auth_admin.get('/api/premium/pickup-requests/')
    assert pending.status_code == 200
    assert any(row['id'] == request_id for row in pending.data)

    decision = auth_admin.post(f'/api/premium/pickup-requests/{request_id}/decide/', {'status': 'approved'}, format='json')
    assert decision.status_code == 200
    assert decision.data['status'] == 'approved'
    assert shift.slots.filter(worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED).exists()
    policy.refresh_from_db()


@pytest.mark.django_db
def test_shift_task_list_flow(auth_admin, auth_worker, shift, location, worker_user):
    created = auth_admin.post('/api/premium/task-lists/', {
        'name': 'Schichtabschluss',
        'kind': 'shift',
        'location_id': str(location.id),
        'items': [
            {'title': 'Arbeitsplatz prüfen', 'required': True},
            {'title': 'Material melden', 'required': True},
        ],
    }, format='json')
    assert created.status_code == 201

    assigned = auth_admin.post(f"/api/premium/task-lists/{created.data['id']}/assign/", {
        'shift_id': str(shift.id),
        'worker_id': str(worker_user.worker_profile.id),
    }, format='json')
    assert assigned.status_code == 201

    runs = auth_worker.get('/api/premium/task-runs/')
    assert runs.status_code == 200
    run = next(row for row in runs.data if row['id'] == assigned.data['id'])
    assert len(run['items']) == 2

    for item in run['items']:
        completed = auth_worker.post(f"/api/premium/task-runs/{run['id']}/complete/", {'item_id': item['id']}, format='json')
        assert completed.status_code == 200
    assert completed.data['run_closed'] is True


@pytest.mark.django_db
def test_staff_callout_reopens_capacity(auth_worker, shift, worker_user):
    assert shift.slots.filter(worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED).exists()
    response = auth_worker.post('/api/premium/callouts/', {
        'shift_id': str(shift.id),
        'reason': 'Krank',
    }, format='json')
    assert response.status_code == 201
    assert response.data['status'] == 'open'
    assert shift.slots.filter(worker__isnull=True, status=ShiftSlot.Status.OPEN).exists()


@pytest.mark.django_db
def test_public_api_key_is_hashed_and_scoped(auth_admin, worker_user):
    issued = auth_admin.post('/api/premium/api-keys/', {
        'name': 'HR read only',
        'scopes': ['users:read'],
    }, format='json')
    assert issued.status_code == 201
    raw = issued.data['key']
    assert raw.startswith('aplus_')

    client = APIClient()
    response = client.get('/api/public/v1/users/', HTTP_X_API_KEY=raw)
    assert response.status_code == 200
    assert any(row['email'] == worker_user.email for row in response.data['results'])

    denied = client.post('/api/public/v1/shifts/', {}, format='json', HTTP_X_API_KEY=raw)
    assert denied.status_code in {401, 403}


@pytest.mark.django_db
def test_saml_status_is_safe_when_unconfigured(api_client):
    response = api_client.get('/api/auth/saml/status/')
    assert response.status_code == 200
    assert response.data['enabled'] is False
