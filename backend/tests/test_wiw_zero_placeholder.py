from unittest.mock import Mock

import pytest

from core.models import ClientCompany, Location, Position, Shift, User, WorkerProfile
from core.shift_slots import ShiftSlot
from core.wiw_schedule_sync import WhenIWorkSynchronizer


def client_stub():
    client = Mock()
    client.collection.side_effect = lambda name, params=None, optional=False: type('Result', (), {'items': []})()
    return client


@pytest.mark.django_db
def test_operational_sync_never_creates_wiw_zero_worker():
    sync = WhenIWorkSynchronizer(client=client_stub())

    sync.sync_users([
        {
            'id': 0,
            'first_name': 'Open',
            'last_name': 'Shift',
            'email': '',
            'active': True,
        }
    ])

    assert not User.objects.filter(wiw_id='0').exists()
    assert not User.objects.filter(email__iexact='wiw-0@sync.invalid').exists()
    assert not WorkerProfile.objects.filter(wiw_user_id='0').exists()


@pytest.mark.django_db
def test_wiw_zero_shift_is_open_and_does_not_match_local_worker_without_wiw_id():
    # A local-only worker deliberately has wiw_user_id=NULL. WIW user 0 must not
    # be normalized to None, otherwise the base importer could select this row.
    user = User.objects.create_user(email='local.worker@example.com', password='test')
    local_worker = WorkerProfile.objects.create(user=user, employee_number='LOCAL-001')
    assert local_worker.wiw_user_id is None

    client = ClientCompany.objects.create(name='Martha', customer_number='TEST-MARTHA')
    location = Location.objects.create(
        client=client,
        name='Evangelische Akademie',
        address='Frankfurt am Main',
        wiw_location_id='loc-10',
    )
    position = Position.objects.create(name='Servicekraft test', wiw_position_id='pos-20')

    sync = WhenIWorkSynchronizer(client=client_stub())
    sync.locations['loc-10'] = location
    sync.positions['pos-20'] = position

    sync.sync_shifts([
        {
            'id': 'shift-zero-worker',
            'user_id': 0,
            'location_id': 'loc-10',
            'position_id': 'pos-20',
            'start_time': '2026-09-25T07:30:00+02:00',
            'end_time': '2026-09-25T16:00:00+02:00',
            'published': True,
        }
    ])

    shift = Shift.objects.get(wiw_shift_id='shift-zero-worker')
    assert shift.worker_id is None
    assert shift.is_open is True
    assert shift.status == Shift.Status.PUBLISHED

    slot = ShiftSlot.objects.get(shift=shift, status=ShiftSlot.Status.OPEN)
    assert slot.worker_id is None
    assert slot.wiw_shift_id == 'shift-zero-worker'
