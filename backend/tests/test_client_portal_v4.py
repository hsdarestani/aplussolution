from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import ClientOrder, Location, Notification, Shift, User, WorkerProfile
from core.portal_models import ClientPortalAccess, ClientShiftChangeRequest
from core.shift_slots import ShiftSlot


pytestmark = pytest.mark.django_db


def test_restricted_client_only_sees_scoped_location_and_cannot_mutate(client_user, company, location, position):
    allowed = Location.objects.create(client=company, name='Evangelische Akademie', address='Frankfurt')
    other = Location.objects.create(client=company, name='Andere Location', address='Frankfurt')
    ClientPortalAccess.objects.create(user=client_user, client=company, read_only=True, location_scope=allowed, label='Evangelische Akademie')
    now = timezone.now() + timedelta(days=1)
    visible = Shift.objects.create(client=company, location=allowed, position=position, starts_at=now, ends_at=now + timedelta(hours=4), status=Shift.Status.PUBLISHED, is_open=True, notes='Nur dieser Einsatz')
    Shift.objects.create(client=company, location=other, position=position, starts_at=now, ends_at=now + timedelta(hours=4), status=Shift.Status.PUBLISHED, is_open=True)

    api = APIClient()
    api.force_authenticate(client_user)
    response = api.get('/api/portal/client-shifts/')
    assert response.status_code == 200
    assert [row['id'] for row in response.json()] == [str(visible.id)]
    assert response.json()[0]['notes'] == 'Nur dieser Einsatz'

    blocked = api.post('/api/orders/', {}, format='json')
    assert blocked.status_code == 403
    blocked_docs = api.get('/api/documents/')
    assert blocked_docs.status_code == 403


def test_client_order_notifies_admin_and_approval_creates_multislot_openshift(admin_user, client_user, company, location, position):
    order = ClientOrder.objects.create(
        client=company,
        title='Abendservice',
        description='Bitte schwarze Kleidung',
        location=location,
        starts_at=timezone.now() + timedelta(days=2),
        ends_at=timezone.now() + timedelta(days=2, hours=6),
        requested_staff=3,
        functions=[str(position.id)],
        status=ClientOrder.Status.NEW,
        created_by=client_user,
    )
    assert Notification.objects.filter(user=admin_user, kind=f'client-order-request-{order.id}').exists()

    api = APIClient()
    api.force_authenticate(admin_user)
    response = api.post(
        f'/api/portal/admin/client-requests/{order.id}/decision/',
        {'decision': 'approve', 'position': str(position.id)},
        format='json',
    )
    assert response.status_code == 200
    order.refresh_from_db()
    shift = order.shifts.get()
    assert order.status == ClientOrder.Status.CONFIRMED
    assert shift.status == Shift.Status.PUBLISHED
    assert shift.is_open is True
    assert shift.worker_id is None
    assert shift.required_count == 3
    assert shift.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).count() == 3


def test_client_shift_change_request_keeps_requester_history_and_applies_after_admin_approval(admin_user, client_user, company, location, position):
    start = timezone.now() + timedelta(days=3)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=5),
        status=Shift.Status.PUBLISHED,
        is_open=True,
        notes='Original note',
    )
    new_start = start + timedelta(hours=1)
    new_end = new_start + timedelta(hours=6)

    client_api = APIClient()
    client_api.force_authenticate(client_user)
    created = client_api.post('/api/portal/shift-change-requests/', {
        'shift': str(shift.id),
        'request_type': 'change',
        'starts_at': new_start.isoformat(),
        'ends_at': new_end.isoformat(),
        'note': 'Eine Stunde später bitte',
    }, format='json')
    assert created.status_code == 201
    request_id = created.json()['id']
    row = ClientShiftChangeRequest.objects.get(pk=request_id)
    assert row.requested_by == client_user
    assert row.original_snapshot['notes'] == 'Original note'
    assert Notification.objects.filter(user=admin_user, kind=f'client-shift-request-{row.id}').exists()

    admin_api = APIClient()
    admin_api.force_authenticate(admin_user)
    decided = admin_api.post(f'/api/portal/admin/shift-change-requests/{row.id}/decision/', {'decision': 'approve'}, format='json')
    assert decided.status_code == 200
    shift.refresh_from_db()
    row.refresh_from_db()
    assert shift.starts_at == new_start
    assert shift.ends_at == new_end
    assert row.status == ClientShiftChangeRequest.Status.APPROVED
    assert row.decided_by == admin_user
    assert row.decision_snapshot['starts_at'] == new_start.isoformat()

    history = admin_api.get('/api/portal/admin/shift-change-requests/').json()['history']
    item = next(value for value in history if value['id'] == str(row.id))
    assert item['requested_by_name'] == 'Klara'
    assert item['requested_by_email'] == client_user.email
    assert item['created_at']


def test_rating_candidates_group_workers_by_shift_and_include_notes(client_user, company, location, position):
    first_user = User.objects.create_user('rating1@example.com', 'StrongPass123!', first_name='Anna', last_name='Test', role=User.Role.WORKER)
    second_user = User.objects.create_user('rating2@example.com', 'StrongPass123!', first_name='Ben', last_name='Test', role=User.Role.WORKER)
    first = WorkerProfile.objects.create(user=first_user, employee_number='RATE-1')
    second = WorkerProfile.objects.create(user=second_user, employee_number='RATE-2')
    end = timezone.now() - timedelta(hours=1)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=end - timedelta(hours=5),
        ends_at=end,
        status=Shift.Status.CONFIRMED,
        worker=first,
        notes='VIP Empfang',
        required_count=2,
    )
    ShiftSlot.objects.create(shift=shift, worker=first, status=ShiftSlot.Status.CLAIMED, source='admin')
    ShiftSlot.objects.create(shift=shift, worker=second, status=ShiftSlot.Status.CLAIMED, source='admin')

    api = APIClient()
    api.force_authenticate(client_user)
    response = api.get('/api/portal/rating-candidates/')
    assert response.status_code == 200
    rows = [row for row in response.json() if row['shift_id'] == str(shift.id)]
    assert {row['worker_name'] for row in rows} == {'Anna Test', 'Ben Test'}
    assert {row['notes'] for row in rows} == {'VIP Empfang'}
