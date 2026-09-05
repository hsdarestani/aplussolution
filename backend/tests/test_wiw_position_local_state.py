import pytest

from core.models import Position
from core.wiw_position_protection import install_wiw_position_protection
from core.wiw_sync import WhenIWorkSynchronizer


@pytest.mark.django_db
def test_existing_inactive_position_is_not_reactivated_by_wiw():
    install_wiw_position_protection()
    position = Position.objects.create(
        name='Garderobe',
        active=False,
        wiw_position_id='101',
    )

    sync = WhenIWorkSynchronizer(client=object())
    sync.sync_positions([
        {'id': '101', 'name': 'Garderobe', 'active': True, 'color': '#111111'},
    ])

    position.refresh_from_db()
    assert position.active is False
    assert position.color == '#111111'


@pytest.mark.django_db
def test_existing_active_position_is_not_deactivated_by_wiw():
    install_wiw_position_protection()
    position = Position.objects.create(
        name='Service',
        active=True,
        wiw_position_id='102',
    )

    sync = WhenIWorkSynchronizer(client=object())
    sync.sync_positions([
        {'id': '102', 'name': 'Service', 'active': False},
    ])

    position.refresh_from_db()
    assert position.active is True


@pytest.mark.django_db
def test_new_position_can_take_initial_active_state_from_wiw():
    install_wiw_position_protection()

    sync = WhenIWorkSynchronizer(client=object())
    sync.sync_positions([
        {'id': '103', 'name': 'Neue WIW Position', 'active': False},
    ])

    position = Position.objects.get(wiw_position_id='103')
    assert position.active is False
