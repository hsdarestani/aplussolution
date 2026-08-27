from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import ClientCompany, Location, Position, Shift, TimeEntry, User, WorkerProfile
from core.wiw_scope_reconciliation import reconcile_wiw_history_scope
from core.workforce_scope import CANONICAL_CLIENTS, CANONICAL_POSITIONS


@pytest.mark.django_db
def test_wiw_history_scope_relinks_known_aliases_and_preserves_history():
    canonical_client = ClientCompany.objects.create(name='OMMIA Frankfurt', customer_number='KD-SCOPE-03', active=True)
    alias_client = ClientCompany.objects.create(name='ommia fankfurt', customer_number='WIW-30', active=True)
    legacy_client = ClientCompany.objects.create(name='Kunde Alpha Alt', customer_number='WIW-31', active=True)

    alias_location = Location.objects.create(
        client=alias_client,
        name='OMMIA Eventfläche',
        address='Frankfurt am Main',
        active=True,
        wiw_location_id='30',
    )
    legacy_location = Location.objects.create(
        client=legacy_client,
        name='Legacy Einsatzort',
        address='Frankfurt am Main',
        active=True,
        wiw_location_id='31',
    )

    canonical_position = Position.objects.create(name='Servicekraft', color='#155eef', active=True)
    alias_position = Position.objects.create(name='Servicekrat', active=True, wiw_position_id='20')
    legacy_position = Position.objects.create(name='Hostess', active=True, wiw_position_id='21')

    user = User.objects.create_user(email='history@example.test', first_name='History', last_name='Worker')
    worker = WorkerProfile.objects.create(user=user, employee_number='WIW-HIST-1', wiw_user_id='10')
    starts_at = timezone.now() - timedelta(days=30)
    shift = Shift.objects.create(
        client=alias_client,
        location=alias_location,
        position=alias_position,
        worker=worker,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=5),
        status=Shift.Status.COMPLETED,
        wiw_shift_id='40',
    )
    TimeEntry.objects.create(
        worker=worker,
        shift=shift,
        clock_in=starts_at,
        clock_out=starts_at + timedelta(hours=5),
        wiw_time_id='50',
    )

    result = reconcile_wiw_history_scope()

    shift.refresh_from_db()
    alias_client.refresh_from_db()
    legacy_client.refresh_from_db()
    alias_position.refresh_from_db()
    legacy_position.refresh_from_db()
    alias_location.refresh_from_db()
    legacy_location.refresh_from_db()

    assert result['valid'] is True
    assert shift.client_id == canonical_client.id
    assert shift.position_id == canonical_position.id
    assert alias_location.client_id == canonical_client.id
    assert alias_location.active is True
    assert legacy_location.active is False
    assert alias_client.active is False and alias_client.customer_number == 'WIW-30'
    assert legacy_client.active is False
    assert alias_position.active is False and alias_position.wiw_position_id == '20'
    assert legacy_position.active is False and legacy_position.wiw_position_id == '21'
    assert Shift.objects.filter(wiw_shift_id='40').count() == 1
    assert TimeEntry.objects.filter(wiw_time_id='50').count() == 1
    assert result['history']['shifts_before'] == result['history']['shifts_after'] == 1
    assert result['history']['time_entries_before'] == result['history']['time_entries_after'] == 1
    assert set(ClientCompany.objects.filter(active=True).values_list('name', flat=True)) == set(CANONICAL_CLIENTS)
    assert set(Position.objects.filter(active=True).values_list('name', flat=True)) == set(CANONICAL_POSITIONS)

    second = reconcile_wiw_history_scope()
    assert second['valid'] is True
    assert Shift.objects.filter(wiw_shift_id='40').count() == 1
    assert TimeEntry.objects.filter(wiw_time_id='50').count() == 1
