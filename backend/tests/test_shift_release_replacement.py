from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Notification, Shift
from core.premium_approval_models import ShiftReleaseRequest
from core.shift_slots import ShiftSlot


def assign_native_slot(shift, worker):
    slot = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at').first()
    assert slot is not None
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'test_assignment'
    slot.claimed_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    return slot


@pytest.mark.django_db
def test_release_candidates_and_approved_transfer_keep_assignment_until_admin(
    auth_worker, auth_admin, worker_user, second_worker, shift
):
    original_worker = worker_user.worker_profile
    slot = assign_native_slot(shift, original_worker)

    candidates = auth_worker.get(f'/api/employee/shifts/{shift.id}/release-candidates/')
    assert candidates.status_code == 200
    ids = {row['id'] for row in candidates.data['candidates']}
    assert str(second_worker.id) in ids
    assert str(original_worker.id) not in ids

    requested = auth_worker.post(
        f'/api/employee/shifts/{shift.id}/release-request/',
        {'requested_worker': str(second_worker.id)},
        format='json',
    )
    assert requested.status_code == 202
    assert requested.data['requested_worker_id'] == str(second_worker.id)

    row = ShiftReleaseRequest.objects.get(pk=requested.data['id'])
    assert row.status == ShiftReleaseRequest.Status.PENDING
    assert row.requested_worker_id == second_worker.id

    # A request alone must never change the live Dienstplan assignment.
    slot.refresh_from_db()
    shift.refresh_from_db()
    assert slot.worker_id == original_worker.id
    assert slot.status == ShiftSlot.Status.CLAIMED
    assert shift.worker_id == original_worker.id

    approved = auth_admin.post(
        f'/api/premium/release-requests/{row.id}/decide/',
        {'status': 'approved'},
        format='json',
    )
    assert approved.status_code == 200
    assert approved.data['transferred_to'] == str(second_worker.id)

    row.refresh_from_db()
    slot.refresh_from_db()
    shift.refresh_from_db()
    assert row.status == ShiftReleaseRequest.Status.APPROVED
    assert slot.worker_id == second_worker.id
    assert slot.status == ShiftSlot.Status.CLAIMED
    assert slot.source == 'admin_approved_transfer'
    assert shift.worker_id == second_worker.id
    assert shift.is_open is False
    assert Notification.objects.filter(
        user=second_worker.user,
        kind=f'shift-release-transfer-{row.id}',
    ).exists()


@pytest.mark.django_db
def test_release_without_requested_worker_returns_slot_to_open_pool(
    auth_worker, auth_admin, worker_user, shift
):
    original_worker = worker_user.worker_profile
    slot = assign_native_slot(shift, original_worker)

    requested = auth_worker.post(
        f'/api/employee/shifts/{shift.id}/release-request/',
        {},
        format='json',
    )
    assert requested.status_code == 202
    row = ShiftReleaseRequest.objects.get(pk=requested.data['id'])
    assert row.requested_worker_id is None

    approved = auth_admin.post(
        f'/api/premium/release-requests/{row.id}/decide/',
        {'status': 'approved'},
        format='json',
    )
    assert approved.status_code == 200
    assert approved.data['transferred_to'] is None

    slot.refresh_from_db()
    shift.refresh_from_db()
    assert slot.worker_id is None
    assert slot.status == ShiftSlot.Status.OPEN
    assert shift.worker_id is None
    assert shift.status == Shift.Status.PUBLISHED
    assert shift.is_open is True


@pytest.mark.django_db
def test_requested_replacement_is_revalidated_on_admin_approval(
    auth_worker, auth_admin, worker_user, second_worker, shift, company, location, position
):
    original_worker = worker_user.worker_profile
    slot = assign_native_slot(shift, original_worker)

    requested = auth_worker.post(
        f'/api/employee/shifts/{shift.id}/release-request/',
        {'requested_worker': str(second_worker.id)},
        format='json',
    )
    assert requested.status_code == 202
    row = ShiftReleaseRequest.objects.get(pk=requested.data['id'])

    # The colleague becomes unavailable after the request was created.
    Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=second_worker,
        starts_at=shift.starts_at + timedelta(minutes=15),
        ends_at=shift.ends_at - timedelta(minutes=15),
        status=Shift.Status.CONFIRMED,
    )

    denied = auth_admin.post(
        f'/api/premium/release-requests/{row.id}/decide/',
        {'status': 'approved'},
        format='json',
    )
    assert denied.status_code == 400

    row.refresh_from_db()
    slot.refresh_from_db()
    shift.refresh_from_db()
    assert row.status == ShiftReleaseRequest.Status.PENDING
    assert slot.worker_id == original_worker.id
    assert slot.status == ShiftSlot.Status.CLAIMED
    assert shift.worker_id == original_worker.id
