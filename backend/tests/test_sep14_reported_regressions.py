from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Notification, Shift
from core.operational_notifications import notify_claimed_workers_shift_changed
from core.shift_service import refresh_shift_state
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_wiw_refresh_cannot_take_back_admin_reassignment(
    auth_admin, company, location, position, worker_user, second_worker
):
    """Mirror the production Arina -> Musa failure on an imported WIW card."""
    original_worker = worker_user.worker_profile
    starts = timezone.now() + timedelta(days=1)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=original_worker,
        starts_at=starts,
        ends_at=starts + timedelta(hours=7),
        required_count=1,
        status=Shift.Status.CONFIRMED,
        wiw_shift_id='sep14-arina-musa-regression',
        schedule_groups=['service'],
    )
    slot = ShiftSlot.objects.get(shift=shift)
    assert slot.worker_id == original_worker.id
    assert slot.source == 'wiw'

    replaced = auth_admin.post(
        f'/api/shifts/{shift.id}/assign/',
        {'workers': [str(second_worker.id)], 'publish_remaining': True},
        format='json',
    )
    assert replaced.status_code == 200, replaced.data

    slot.refresh_from_db()
    shift.refresh_from_db()
    assert slot.worker_id == second_worker.id
    assert slot.source == 'admin_assignment'
    assert shift.worker_id == second_worker.id

    # Simulate the next WIW import attempting to restore the old remote worker.
    # The local/native slot must remain authoritative after an explicit admin edit.
    shift.worker = original_worker
    shift.status = Shift.Status.CONFIRMED
    shift.is_open = False
    shift.save(update_fields=['worker', 'status', 'is_open', 'updated_at'])

    slot.refresh_from_db()
    shift.refresh_from_db()
    assert slot.worker_id == second_worker.id
    assert slot.source == 'admin_assignment'
    assert shift.worker_id == second_worker.id

    start_day = timezone.localtime(starts).date().isoformat()
    listed = auth_admin.get(
        f'/api/admin/mobile-schedule/?date_from={start_day}&date_to={start_day}'
    )
    assert listed.status_code == 200, listed.data
    row = next(item for item in listed.data['shifts'] if str(item['id']) == str(shift.id))
    claimed = next(card for card in row['slot_cards'] if not card['is_open'])
    assert claimed['worker']['id'] == str(second_worker.id)


@pytest.mark.django_db
def test_identical_shift_update_notifications_are_coalesced(
    company, location, position, worker_user
):
    worker = worker_user.worker_profile
    starts = timezone.now() + timedelta(days=2)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts,
        ends_at=starts + timedelta(hours=6),
        required_count=1,
        status=Shift.Status.PUBLISHED,
        schedule_groups=['service'],
    )
    slot = ShiftSlot.objects.get(shift=shift)
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'admin_assignment'
    slot.save(update_fields=['worker', 'status', 'source', 'updated_at'])
    refresh_shift_state(shift)

    notify_claimed_workers_shift_changed(shift)
    notify_claimed_workers_shift_changed(shift)

    duplicate_qs = Notification.objects.filter(
        user=worker.user,
        kind__startswith='shift-event-updated-',
        title='Schicht aktualisiert',
    )
    assert duplicate_qs.count() == 1

    # A genuinely different shift state still deserves a new notification.
    shift.starts_at = shift.starts_at + timedelta(minutes=30)
    shift.ends_at = shift.ends_at + timedelta(minutes=30)
    shift.save(update_fields=['starts_at', 'ends_at', 'updated_at'])
    notify_claimed_workers_shift_changed(shift)
    assert duplicate_qs.count() == 2
