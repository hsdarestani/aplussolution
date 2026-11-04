"""Regression coverage for stale legacy assignments and genuine employee clashes."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from core.models import Shift
from core.shift_slots import ShiftSlot


def request_payload(company, location, position):
    start = datetime(2026, 11, 19, 8, 0, tzinfo=ZoneInfo('Europe/Berlin'))
    return {
        'client': str(company.id),
        'location': str(location.id),
        'position': str(position.id),
        'starts_at': start.isoformat(),
        'ends_at': (start + timedelta(hours=5)).isoformat(),
        'required_count': 1,
        'status': 'draft',
        'schedule_groups': ['housekeeping'],
    }


@pytest.mark.django_db
def test_admin_can_assign_worker_on_november_19_despite_stale_legacy_mirror(
    auth_admin, worker_user, company, location, position,
):
    payload = request_payload(company, location, position)
    old = auth_admin.post('/api/shifts/', payload, format='json')
    assert old.status_code == 201, old.data

    # Simulate a migrated/stale Shift.worker field. The actual ShiftSlot is OPEN
    # and the worker has not been assigned to this historical record.
    old_id = old.data['id']
    assert ShiftSlot.objects.filter(shift_id=old_id, status=ShiftSlot.Status.OPEN).exists()
    Shift.objects.filter(pk=old_id).update(worker=worker_user.worker_profile)
    assert not ShiftSlot.objects.filter(
        shift_id=old_id, worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED,
    ).exists()

    created = auth_admin.post(
        '/api/shifts/', {**payload, 'workers': [str(worker_user.worker_profile.id)]},
        format='json',
    )
    assert created.status_code == 201, created.data
    assert created.data['assigned_workers'][0]['id'] == str(worker_user.worker_profile.id)


@pytest.mark.django_db
def test_real_overlap_still_blocks_november_19_with_worker_name_not_admin_du(
    auth_admin, worker_user, company, location, position,
):
    payload = request_payload(company, location, position)
    first = auth_admin.post(
        '/api/shifts/', {**payload, 'workers': [str(worker_user.worker_profile.id)]},
        format='json',
    )
    assert first.status_code == 201, first.data

    overlap = auth_admin.post(
        '/api/shifts/', {**payload, 'workers': [str(worker_user.worker_profile.id)]},
        format='json',
    )
    assert overlap.status_code == 400, overlap.data
    detail = str(overlap.data)
    assert 'Anna Becker' in detail
    assert 'andere Schicht' in detail
    assert 'Du hast' not in detail


@pytest.mark.django_db
def test_reassign_same_person_does_not_trigger_self_overlap(
    auth_admin, worker_user, company, location, position,
):
    payload = request_payload(company, location, position)
    created = auth_admin.post(
        '/api/shifts/', {**payload, 'workers': [str(worker_user.worker_profile.id)]},
        format='json',
    )
    assert created.status_code == 201, created.data
    slot_id = created.data['slot_cards'][0]['id']
    edited = auth_admin.patch(
        f"/api/shifts/{created.data['id']}/cards/{slot_id}/",
        {'notes': 'Updated by admin; unchanged worker'},
        format='json',
    )
    assert edited.status_code == 200, edited.data
    assert edited.data['shift']['assigned_workers'][0]['id'] == str(worker_user.worker_profile.id)
