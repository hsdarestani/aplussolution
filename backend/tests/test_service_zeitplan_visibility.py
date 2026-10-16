from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Shift, User, WorkerProfile
from core.shift_slots import ShiftSlot


def _claimed_shift(*, company, location, position, worker, offset_hours):
    starts_at = timezone.now() + timedelta(hours=offset_hours)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=6),
        status=Shift.Status.CONFIRMED,
        required_count=1,
        schedule_groups=['service'] if 'service' in (worker.schedule_groups or []) else [],
    )
    slot = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).first()
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'admin_assignment'
    slot.claimed_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    return shift


@pytest.mark.django_db
def test_service_worker_sees_own_and_service_peer_but_not_other_schedule(worker_user, company, location, position):
    requester = worker_user.worker_profile
    requester.schedule_groups = ['service']
    requester.save(update_fields=['schedule_groups'])

    peer_user = User.objects.create_user(
        'service-peer@example.com', 'StrongPass123!', first_name='Ben', last_name='Neumann', role=User.Role.WORKER
    )
    peer = WorkerProfile.objects.create(
        user=peer_user, employee_number='MA-SERVICE-2', schedule_groups=['service'], active=True
    )
    other_user = User.objects.create_user(
        'housekeeping-peer@example.com', 'StrongPass123!', first_name='Cara', last_name='Klein', role=User.Role.WORKER
    )
    other = WorkerProfile.objects.create(
        user=other_user, employee_number='MA-HK-1', schedule_groups=['housekeeping'], active=True
    )

    own_shift = _claimed_shift(company=company, location=location, position=position, worker=requester, offset_hours=2)
    peer_shift = _claimed_shift(company=company, location=location, position=position, worker=peer, offset_hours=10)
    other_shift = _claimed_shift(company=company, location=location, position=position, worker=other, offset_hours=18)

    client = APIClient()
    client.force_authenticate(worker_user)
    response = client.get('/api/employee/schedule/')

    assert response.status_code == 200
    assert response.data['service_schedule'] is True
    ids = {str(row['id']) for row in response.data['shifts']}
    assert str(own_shift.id) in ids
    assert str(peer_shift.id) in ids
    assert str(other_shift.id) not in ids

    peer_row = next(row for row in response.data['shifts'] if str(row['id']) == str(peer_shift.id))
    assert peer_row['assigned_workers'][0]['name'] == 'Ben Neumann'
    assert peer_row['assigned_workers'][0]['is_me'] is False


@pytest.mark.django_db
def test_non_service_worker_keeps_own_shift_scope(worker_user, second_worker, company, location, position):
    requester = worker_user.worker_profile
    requester.schedule_groups = ['housekeeping']
    requester.save(update_fields=['schedule_groups'])
    second_worker.schedule_groups = ['housekeeping']
    second_worker.save(update_fields=['schedule_groups'])

    own_shift = _claimed_shift(company=company, location=location, position=position, worker=requester, offset_hours=2)
    peer_shift = _claimed_shift(company=company, location=location, position=position, worker=second_worker, offset_hours=10)

    client = APIClient()
    client.force_authenticate(worker_user)
    response = client.get('/api/employee/schedule/')

    assert response.status_code == 200
    assert response.data['service_schedule'] is False
    ids = {str(row['id']) for row in response.data['shifts']}
    assert ids == {str(own_shift.id)}
    assert str(peer_shift.id) not in ids


@pytest.mark.django_db
def test_service_schedule_expands_multi_worker_shift_for_legacy_mobile(
    worker_user, company, location, position
):
    requester = worker_user.worker_profile
    requester.schedule_groups = ['service']
    requester.save(update_fields=['schedule_groups'])

    peer1_user = User.objects.create_user(
        'peer-one@example.com', 'StrongPass123!', first_name='Anna', last_name='Eins', role=User.Role.WORKER
    )
    peer1 = WorkerProfile.objects.create(
        user=peer1_user, employee_number='MA-SERVICE-A', schedule_groups=['service'], active=True
    )
    peer2_user = User.objects.create_user(
        'peer-two@example.com', 'StrongPass123!', first_name='Yohannes', last_name='Kiffle', role=User.Role.WORKER
    )
    peer2 = WorkerProfile.objects.create(
        user=peer2_user, employee_number='MA-SERVICE-B', schedule_groups=['service'], active=True
    )

    starts_at = timezone.now() + timedelta(hours=3)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=5),
        status=Shift.Status.CONFIRMED,
        required_count=2,
        schedule_groups=['service'],
    )
    slots = list(shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at'))
    for slot, peer in zip(slots, [peer1, peer2]):
        slot.worker = peer
        slot.status = ShiftSlot.Status.CLAIMED
        slot.source = 'admin_assignment'
        slot.claimed_at = timezone.now()
        slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])

    client = APIClient()
    client.force_authenticate(worker_user)
    response = client.get('/api/employee/schedule/')

    assert response.status_code == 200
    rows = [
        row for row in response.data['shifts']
        if str(row.get('source_shift_id') or row['id']) == str(shift.id)
    ]
    assert len(rows) == 2
    assert {row['assigned_workers'][0]['name'] for row in rows} == {'Anna Eins', 'Yohannes Kiffle'}
    assert len({str(row['id']) for row in rows}) == 2
    assert all(len(row['assigned_workers']) == 1 for row in rows)


@pytest.mark.django_db
def test_service_worker_sees_two_distinct_open_slots_in_legacy_service_zeitplan(
    worker_user, company, location, position
):
    requester = worker_user.worker_profile
    requester.schedule_groups = ['service']
    requester.save(update_fields=['schedule_groups'])

    starts_at = timezone.now() + timedelta(days=4)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=4, minutes=30),
        status=Shift.Status.PUBLISHED,
        required_count=2,
        schedule_groups=['service'],
    )

    client = APIClient()
    client.force_authenticate(worker_user)
    response = client.get('/api/employee/schedule/')
    assert response.status_code == 200
    cards = [
        row for row in response.data['shifts']
        if row.get('_available_open_slot') and str(row.get('source_shift_id')) == str(shift.id)
    ]
    slot_ids = {
        str(slot.id) for slot in shift.slots.filter(
            status=ShiftSlot.Status.OPEN, worker__isnull=True
        )
    }
    assert len(cards) == 2
    assert {str(card['id']) for card in cards} == slot_ids
    assert all(card['open_count'] == 1 and card['filled_count'] == 0 for card in cards)
    assert all(card['assigned_workers'][0]['name'] == 'OpenShift' for card in cards)
    assert all(not card['assigned_workers'][0]['is_me'] for card in cards)

    available = client.get('/api/shifts/available/')
    assert available.status_code == 200
    results = available.data.get('results', []) if isinstance(available.data, dict) else available.data
    open_rows = [row for row in results if row.get('source_shift_id') == str(shift.id)]
    assert len(open_rows) == 2
    assert {row['id'] for row in open_rows} == slot_ids
    assert all(row['open_count'] == 1 for row in open_rows)
    assert all(len(row['slot_cards']) == 1 and row['slot_cards'][0]['is_open'] for row in open_rows)


@pytest.mark.django_db
def test_service_worker_does_not_see_housekeeping_open_slots(
    worker_user, company, location, position
):
    requester = worker_user.worker_profile
    requester.schedule_groups = ['service']
    requester.save(update_fields=['schedule_groups'])
    starts_at = timezone.now() + timedelta(days=4)
    housekeeping_shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=5),
        status=Shift.Status.PUBLISHED,
        required_count=2,
        schedule_groups=['housekeeping'],
    )

    client = APIClient()
    client.force_authenticate(worker_user)
    response = client.get('/api/employee/schedule/')
    assert response.status_code == 200
    assert not any(
        str(row.get('source_shift_id')) == str(housekeeping_shift.id)
        for row in response.data['shifts']
    )
