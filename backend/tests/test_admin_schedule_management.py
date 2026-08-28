from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Availability, Shift
from core.shift_service import ensure_slots
from core.shift_slots import ShiftSlot


@pytest.mark.django_db
def test_admin_can_create_edit_list_and_delete_worker_availability(auth_admin, worker_user):
    worker = worker_user.worker_profile
    starts = timezone.now() + timedelta(days=2)
    ends = starts + timedelta(hours=6)

    created = auth_admin.post(
        '/api/operations/availability/',
        {
            'worker': str(worker.id),
            'starts_at': starts.isoformat(),
            'ends_at': ends.isoformat(),
            'available': False,
            'note': 'Vom Mitarbeiter gemeldet',
        },
        format='json',
    )

    assert created.status_code == 201
    item_id = created.data['id']
    assert created.data['worker_name'] == 'Anna Becker'
    assert created.data['available'] is False

    listed = auth_admin.get('/api/operations/availability/')
    assert listed.status_code == 200
    assert any(str(row['id']) == str(item_id) for row in listed.data)

    updated = auth_admin.patch(
        f'/api/operations/availability/{item_id}/',
        {
            'worker': str(worker.id),
            'starts_at': (starts + timedelta(hours=1)).isoformat(),
            'ends_at': (ends + timedelta(hours=1)).isoformat(),
            'available': True,
            'note': 'Von Disposition korrigiert',
        },
        format='json',
    )
    assert updated.status_code == 200
    assert updated.data['available'] is True
    assert updated.data['note'] == 'Von Disposition korrigiert'

    deleted = auth_admin.delete(f'/api/operations/availability/{item_id}/')
    assert deleted.status_code == 204
    assert not Availability.objects.filter(pk=item_id).exists()


@pytest.mark.django_db
def test_worker_availability_collection_stays_scoped_to_self(auth_worker, worker_user, second_worker):
    own = Availability.objects.create(
        worker=worker_user.worker_profile,
        starts_at=timezone.now() + timedelta(days=1),
        ends_at=timezone.now() + timedelta(days=1, hours=2),
        available=True,
    )
    Availability.objects.create(
        worker=second_worker,
        starts_at=timezone.now() + timedelta(days=1),
        ends_at=timezone.now() + timedelta(days=1, hours=3),
        available=False,
    )

    response = auth_worker.get('/api/operations/availability/')

    assert response.status_code == 200
    assert [str(row['id']) for row in response.data] == [str(own.id)]


@pytest.mark.django_db
def test_admin_can_delete_one_card_from_multi_person_shift(auth_admin, company, location, position):
    starts = timezone.now() + timedelta(days=3)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts,
        ends_at=starts + timedelta(hours=6),
        required_count=2,
        status=Shift.Status.PUBLISHED,
    )
    ensure_slots(shift)
    slots = list(ShiftSlot.objects.filter(shift=shift).order_by('created_at'))
    assert len(slots) == 2

    response = auth_admin.delete(f'/api/shifts/{shift.id}/cards/{slots[0].id}/delete/')

    assert response.status_code == 200
    shift.refresh_from_db()
    assert shift.required_count == 1
    assert ShiftSlot.objects.filter(shift=shift).exclude(status=ShiftSlot.Status.CANCELLED).count() == 1


@pytest.mark.django_db
def test_admin_deleting_last_card_removes_empty_shift(auth_admin, company, location, position):
    starts = timezone.now() + timedelta(days=4)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts,
        ends_at=starts + timedelta(hours=4),
        required_count=1,
        status=Shift.Status.PUBLISHED,
    )
    ensure_slots(shift)
    slot = ShiftSlot.objects.get(shift=shift)

    response = auth_admin.delete(f'/api/shifts/{shift.id}/cards/{slot.id}/delete/')

    assert response.status_code == 200
    assert response.data['whole_shift'] is True
    assert not Shift.objects.filter(pk=shift.id).exists()
