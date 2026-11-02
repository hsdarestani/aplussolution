"""Fast single-request mobile shift save regression cases."""
from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Shift


def payload(company, location, position):
    starts_at = timezone.now() + timedelta(days=12)
    return {
        'client': str(company.id),
        'location': str(location.id),
        'position': str(position.id),
        'starts_at': starts_at.isoformat(),
        'ends_at': (starts_at + timedelta(hours=4)).isoformat(),
        'required_count': 1,
        'status': 'draft',
        'schedule_groups': ['service'],
    }


@pytest.mark.django_db
def test_mobile_create_with_worker_is_single_atomic_request(
    auth_admin, worker_user, company, location, position,
):
    requested = payload(company, location, position)
    requested['workers'] = [str(worker_user.worker_profile.id)]
    requested['publish_remaining'] = True
    result = auth_admin.post('/api/shifts/', requested, format='json')
    assert result.status_code == 201, result.data
    saved = auth_admin.get(f"/api/shifts/{result.data['id']}/")
    assert saved.status_code == 200
    assert saved.data['status'] == 'confirmed'
    assert [item['id'] for item in saved.data['assigned_workers']] == [str(worker_user.worker_profile.id)]
    assert saved.data['open_count'] == 0


@pytest.mark.django_db
def test_invalid_mobile_worker_rolls_back_new_shift(
    auth_admin, company, location, position,
):
    before = Shift.objects.count()
    requested = payload(company, location, position)
    requested['workers'] = ['00000000-0000-4000-8000-000000000001']
    result = auth_admin.post('/api/shifts/', requested, format='json')
    assert result.status_code == 400, result.data
    assert Shift.objects.count() == before


@pytest.mark.django_db
def test_mobile_edit_reassigns_worker_in_same_patch(
    auth_admin, worker_user, second_worker, company, location, position,
):
    requested = payload(company, location, position)
    requested['workers'] = [str(worker_user.worker_profile.id)]
    created = auth_admin.post('/api/shifts/', requested, format='json')
    assert created.status_code == 201, created.data
    shift_id = created.data['id']
    before = auth_admin.get(f'/api/shifts/{shift_id}/').data
    slot_id = before['slot_cards'][0]['id']
    changed = auth_admin.patch(
        f'/api/shifts/{shift_id}/cards/{slot_id}/',
        {
            'notes': 'Mobile saved in one request',
            'workers': [str(second_worker.id)],
            'publish_remaining': True,
        },
        format='json',
    )
    assert changed.status_code == 200, changed.data
    current = auth_admin.get(f'/api/shifts/{shift_id}/').data
    assert current['notes'] == 'Mobile saved in one request'
    assert [item['id'] for item in current['assigned_workers']] == [str(second_worker.id)]
    assert current['status'] == 'confirmed'
