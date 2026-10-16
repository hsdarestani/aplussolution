"""Regression tests for legacy native OpenShift one-card-per-slot compatibility."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Shift
from core.shift_slots import ShiftSlot


def available_rows(client):
    response = client.get('/api/shifts/available/')
    assert response.status_code == 200
    return response.data.get('results', []) if isinstance(response.data, dict) else response.data


def service_shift(company, location, position, *, required_count=2, groups=None):
    start = timezone.now() + timedelta(days=4)
    return Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=4, minutes=30),
        status=Shift.Status.PUBLISHED,
        required_count=required_count,
        schedule_groups=groups if groups is not None else ['service'],
    )


@pytest.mark.django_db
def test_native_available_endpoint_expands_into_distinct_real_slot_cards(
    worker_user, company, location, position,
):
    worker = worker_user.worker_profile
    worker.schedule_groups = ['service']
    worker.save(update_fields=['schedule_groups'])
    shift = service_shift(company, location, position)
    slot_ids = set(str(id) for id in shift.slots.filter(
        status=ShiftSlot.Status.OPEN
    ).values_list('id', flat=True))

    client = APIClient()
    client.force_authenticate(worker_user)
    rows = [row for row in available_rows(client)
            if row['source_shift_id'] == str(shift.pk)]

    assert len(rows) == 2
    assert {row['id'] for row in rows} == slot_ids
    assert all(row['open_count'] == 1 for row in rows)
    assert all(len(row['slot_cards']) == 1 for row in rows)
    assert all(row['slot_cards'][0]['id'] == row['id'] for row in rows)


@pytest.mark.django_db
def test_native_slot_claim_is_atomic_and_parent_claim_remains_supported(
    worker_user, second_worker, company, location, position, monkeypatch,
):
    monkeypatch.setattr(
        'core.shift_views.get_policy',
        lambda: SimpleNamespace(pickup_approval_required=False),
    )
    worker = worker_user.worker_profile
    worker.schedule_groups = ['service']
    worker.save(update_fields=['schedule_groups'])
    second_worker.schedule_groups = ['service']
    second_worker.save(update_fields=['schedule_groups'])
    shift = service_shift(company, location, position)

    client = APIClient()
    client.force_authenticate(worker_user)
    rows = [row for row in available_rows(client)
            if row['source_shift_id'] == str(shift.pk)]
    selected, remaining = rows
    claimed = client.post(f"/api/shifts/{selected['id']}/claim/", {}, format='json')
    assert claimed.status_code == 200, claimed.data
    assert claimed.data['id'] == str(shift.pk)
    assert ShiftSlot.objects.get(pk=selected['id']).worker_id == worker.id
    assert ShiftSlot.objects.get(pk=remaining['id']).status == ShiftSlot.Status.OPEN

    # A stale card cannot silently claim another open slot.
    repeat = client.post(f"/api/shifts/{selected['id']}/claim/", {}, format='json')
    assert repeat.status_code == 400
    assert ShiftSlot.objects.get(pk=remaining['id']).worker_id is None

    second_client = APIClient()
    second_client.force_authenticate(second_worker.user)
    by_parent = second_client.post(f'/api/shifts/{shift.pk}/claim/', {}, format='json')
    assert by_parent.status_code == 200, by_parent.data
    assert ShiftSlot.objects.get(pk=remaining['id']).worker_id == second_worker.id


@pytest.mark.django_db
def test_housekeeping_slot_is_neither_visible_nor_claimable_to_service_worker(
    worker_user, company, location, position,
):
    worker = worker_user.worker_profile
    worker.schedule_groups = ['service']
    worker.save(update_fields=['schedule_groups'])
    shift = service_shift(company, location, position, groups=['housekeeping'])
    slot = shift.slots.filter(status=ShiftSlot.Status.OPEN).first()
    assert slot is not None

    client = APIClient()
    client.force_authenticate(worker_user)
    rows = available_rows(client)
    assert not any(row['source_shift_id'] == str(shift.pk) for row in rows)
    response = client.post(f'/api/shifts/{slot.pk}/claim/', {}, format='json')
    assert response.status_code == 400
    assert ShiftSlot.objects.get(pk=slot.pk).worker_id is None


@pytest.mark.django_db
def test_open_slots_on_already_claimed_parent_are_hidden_from_same_worker(
    worker_user, second_worker, company, location, position,
):
    worker = worker_user.worker_profile
    worker.schedule_groups = ['service']
    worker.save(update_fields=['schedule_groups'])
    second_worker.schedule_groups = ['service']
    second_worker.save(update_fields=['schedule_groups'])
    shift = service_shift(company, location, position)
    slot = shift.slots.filter(status=ShiftSlot.Status.OPEN).first()
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.save(update_fields=['worker', 'status'])

    mine_client = APIClient()
    mine_client.force_authenticate(worker_user)
    mine = available_rows(mine_client)
    assert not any(row['source_shift_id'] == str(shift.pk) for row in mine)

    peer_client = APIClient()
    peer_client.force_authenticate(second_worker.user)
    peer = available_rows(peer_client)
    rows = [row for row in peer if row['source_shift_id'] == str(shift.pk)]
    assert len(rows) == 1
    assert rows[0]['id'] != str(slot.pk)
