from datetime import datetime, timezone as dt_timezone
from unittest.mock import Mock

import pytest

from core.models import ClientCompany, Location, Position, Shift, User, WorkerProfile
from core.shift_slots import ShiftSlot
from core.wiw_shift_dedup import install_wiw_shift_dedup
from core.wiw_sync import WhenIWorkSynchronizer


@pytest.fixture
def schedule_setup():
    install_wiw_shift_dedup()
    client = ClientCompany.objects.create(
        name='Hotel Test',
        customer_number='DEDUP-CLIENT',
    )
    location = Location.objects.create(
        client=client,
        name='Hotel Test',
        address='Teststr. 1',
        wiw_location_id='30',
    )
    position = Position.objects.create(name='Housekeeping Dedup', wiw_position_id='20')
    return client, location, position


def _worker(email, employee_number, wiw_id):
    user = User.objects.create_user(email=email, password='test-password', first_name='Test')
    return WorkerProfile.objects.create(
        user=user,
        employee_number=employee_number,
        wiw_user_id=wiw_id,
    )


def _incoming(*, wiw_id, worker_id=None, start, end, break_minutes=0, published=True):
    payload = {
        'id': wiw_id,
        'location_id': '30',
        'position_id': '20',
        'start_time': start.isoformat(),
        'end_time': end.isoformat(),
        'break_minutes': break_minutes,
        'published': published,
    }
    if worker_id is not None:
        payload['user_id'] = worker_id
    return payload


@pytest.mark.django_db
def test_identical_assigned_local_shift_is_bound_instead_of_duplicated(schedule_setup):
    client, location, position = schedule_setup
    worker = _worker('dedup-a@example.com', 'DEDUP-A', '10')
    start = datetime(2026, 9, 10, 6, 0, tzinfo=dt_timezone.utc)
    end = datetime(2026, 9, 10, 11, 0, tzinfo=dt_timezone.utc)
    local = Shift.objects.create(
        client=client,
        location=location,
        position=position,
        starts_at=start,
        ends_at=end,
        break_minutes=0,
        status=Shift.Status.CONFIRMED,
        required_count=1,
    )
    slot = local.slots.get(status=ShiftSlot.Status.OPEN)
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'admin_assignment'
    slot.save(update_fields=['worker', 'status', 'source', 'updated_at'])

    sync = WhenIWorkSynchronizer(client=Mock())
    sync.workers['10'] = worker
    sync.locations['30'] = location
    sync.positions['20'] = position
    sync.sync_shifts([_incoming(wiw_id='40', worker_id='10', start=start, end=end)])

    assert sync.errors == []
    assert Shift.objects.count() == 1
    local.refresh_from_db()
    assert local.wiw_shift_id == '40'
    assert local.worker_id == worker.id
    assert sync.counts['shifts_deduplicated'] == 1
    assert ShiftSlot.objects.filter(shift=local, wiw_shift_id='40', worker=worker, status='claimed').count() == 1


@pytest.mark.django_db
def test_identical_open_local_shift_is_bound_instead_of_duplicated(schedule_setup):
    client, location, position = schedule_setup
    start = datetime(2026, 9, 12, 6, 0, tzinfo=dt_timezone.utc)
    end = datetime(2026, 9, 12, 11, 0, tzinfo=dt_timezone.utc)
    local = Shift.objects.create(
        client=client,
        location=location,
        position=position,
        starts_at=start,
        ends_at=end,
        break_minutes=0,
        status=Shift.Status.PUBLISHED,
        required_count=1,
    )

    sync = WhenIWorkSynchronizer(client=Mock())
    sync.locations['30'] = location
    sync.positions['20'] = position
    sync.sync_shifts([_incoming(wiw_id='41', start=start, end=end)])

    assert sync.errors == []
    assert Shift.objects.count() == 1
    local.refresh_from_db()
    assert local.wiw_shift_id == '41'
    assert local.is_open is True
    assert sync.counts['shifts_deduplicated'] == 1
    assert ShiftSlot.objects.filter(shift=local, wiw_shift_id='41', worker__isnull=True, status='open').count() == 1


@pytest.mark.django_db
def test_changed_worker_is_imported_as_distinct_shift(schedule_setup):
    client, location, position = schedule_setup
    local_worker = _worker('dedup-local@example.com', 'DEDUP-LOCAL', '10')
    wiw_worker = _worker('dedup-wiw@example.com', 'DEDUP-WIW', '11')
    start = datetime(2026, 9, 11, 6, 0, tzinfo=dt_timezone.utc)
    end = datetime(2026, 9, 11, 11, 0, tzinfo=dt_timezone.utc)
    local = Shift.objects.create(
        client=client,
        location=location,
        position=position,
        starts_at=start,
        ends_at=end,
        break_minutes=0,
        status=Shift.Status.CONFIRMED,
        required_count=1,
    )
    slot = local.slots.get(status=ShiftSlot.Status.OPEN)
    slot.worker = local_worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'admin_assignment'
    slot.save(update_fields=['worker', 'status', 'source', 'updated_at'])

    sync = WhenIWorkSynchronizer(client=Mock())
    sync.workers['11'] = wiw_worker
    sync.locations['30'] = location
    sync.positions['20'] = position
    sync.sync_shifts([_incoming(wiw_id='42', worker_id='11', start=start, end=end)])

    assert sync.errors == []
    assert Shift.objects.count() == 2
    local.refresh_from_db()
    assert local.wiw_shift_id in (None, '')
    imported = Shift.objects.get(wiw_shift_id='42')
    assert imported.worker_id == wiw_worker.id
    assert sync.counts['shifts_deduplicated'] == 0
    assert sync.counts['shifts_created'] == 1
