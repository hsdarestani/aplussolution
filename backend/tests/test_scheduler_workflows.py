from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Shift
from core.scheduling_models import SchedulingPolicy
from core.shift_slots import ShiftSlot


def shift_for(company, location, position, start, hours=4, status=Shift.Status.PUBLISHED):
    return Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=hours),
        status=status,
        published_at=timezone.now() if status == Shift.Status.PUBLISHED else None,
        is_open=status == Shift.Status.PUBLISHED,
    )


def claim_slot(shift, worker):
    slot = shift.slots.first()
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'test'
    slot.claimed_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    return slot


@pytest.mark.django_db
def test_drag_style_shift_update_rolls_back_when_hard_rest_rule_breaks(auth_admin, worker_user, company, location, position):
    SchedulingPolicy.objects.create(
        name='Hard Rest',
        qualification_mode='off',
        schedule_membership_mode='off',
        skill_tag_mode='off',
        availability_mode='block',
        time_off_mode='block',
        rest_mode='block',
        hours_mode='off',
        days_mode='off',
        min_rest_hours=11,
    )
    first = shift_for(company, location, position, timezone.now() + timedelta(days=4), hours=8)
    claim_slot(first, worker_user.worker_profile)
    second = shift_for(company, location, position, first.ends_at + timedelta(hours=13), hours=4)
    claim_slot(second, worker_user.worker_profile)
    original_start = second.starts_at
    original_end = second.ends_at
    proposed_start = first.ends_at + timedelta(hours=6)
    proposed_end = proposed_start + timedelta(hours=4)

    response = auth_admin.patch(
        f'/api/shifts/{second.id}/',
        {'starts_at': proposed_start.isoformat(), 'ends_at': proposed_end.isoformat()},
        format='json',
    )
    assert response.status_code == 400
    assert 'Mindestruhezeit' in str(response.data)
    second.refresh_from_db()
    assert second.starts_at == original_start
    assert second.ends_at == original_end


@pytest.mark.django_db
def test_bulk_unpublish_skips_staffed_shift(auth_admin, worker_user, company, location, position):
    shift = shift_for(company, location, position, timezone.now() + timedelta(days=5))
    claim_slot(shift, worker_user.worker_profile)
    response = auth_admin.post(
        '/api/scheduling/bulk-action/',
        {'ids': [str(shift.id)], 'action': 'unpublish'},
        format='json',
    )
    assert response.status_code == 200
    assert response.data['changed'] == 0
    assert len(response.data['skipped']) == 1
    shift.refresh_from_db()
    assert shift.status == Shift.Status.PUBLISHED


@pytest.mark.django_db
def test_clear_range_deletes_only_unstaffed_drafts(auth_admin, worker_user, company, location, position):
    start = timezone.now() + timedelta(days=6)
    unstaffed = shift_for(company, location, position, start, status=Shift.Status.DRAFT)
    staffed = shift_for(company, location, position, start + timedelta(hours=6), status=Shift.Status.DRAFT)
    claim_slot(staffed, worker_user.worker_profile)
    response = auth_admin.post(
        '/api/scheduling/clear-range/',
        {
            'starts_at': (start - timedelta(hours=1)).isoformat(),
            'ends_at': (start + timedelta(days=1)).isoformat(),
        },
        format='json',
    )
    assert response.status_code == 200
    assert response.data['deleted'] == 1
    assert not Shift.objects.filter(pk=unstaffed.pk).exists()
    assert Shift.objects.filter(pk=staffed.pk).exists()
    assert ShiftSlot.objects.filter(shift=staffed, worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED).exists()


@pytest.mark.django_db
def test_assignment_details_are_visible_to_manager_but_not_client(auth_admin, auth_client, worker_user, company, location, position):
    shift = shift_for(company, location, position, timezone.now() + timedelta(days=7))
    claim_slot(shift, worker_user.worker_profile)
    manager_response = auth_admin.get('/api/shifts/?ordering=starts_at')
    assert manager_response.status_code == 200
    manager_rows = manager_response.data['results'] if isinstance(manager_response.data, dict) else manager_response.data
    manager_row = next(row for row in manager_rows if row['id'] == str(shift.id))
    assert manager_row['assignments'][0]['worker'] == str(worker_user.worker_profile.id)

    client_response = auth_client.get('/api/shifts/?ordering=starts_at')
    assert client_response.status_code == 200
    client_rows = client_response.data['results'] if isinstance(client_response.data, dict) else client_response.data
    client_row = next(row for row in client_rows if row['id'] == str(shift.id))
    assert client_row['assignments'] == []
