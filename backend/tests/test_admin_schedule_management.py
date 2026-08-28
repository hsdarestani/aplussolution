from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Availability, Shift
from core.shift_service import ensure_slots, refresh_shift_state
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


@pytest.mark.django_db
def test_admin_can_save_edit_for_claimed_single_shift_card(auth_admin, company, location, position, worker_user):
    starts = timezone.now() + timedelta(days=5)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts,
        ends_at=starts + timedelta(hours=6),
        required_count=1,
        status=Shift.Status.PUBLISHED,
        confirmation_required=False,
        schedule_groups=['service'],
    )
    ensure_slots(shift)
    slot = ShiftSlot.objects.get(shift=shift)
    slot.worker = worker_user.worker_profile
    slot.status = ShiftSlot.Status.CLAIMED
    slot.save(update_fields=['worker', 'status', 'updated_at'])
    refresh_shift_state(shift)

    new_start = starts + timedelta(hours=1)
    new_end = new_start + timedelta(hours=6)
    response = auth_admin.patch(
        f'/api/shifts/{shift.id}/cards/{slot.id}/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': new_start.isoformat(),
            'ends_at': new_end.isoformat(),
            'notes': 'Mobile edit saved',
            'confirmation_required': True,
            'schedule_groups': ['service'],
            'status': 'published',
            'apply_all': False,
        },
        format='json',
    )

    assert response.status_code == 200, response.data
    shift.refresh_from_db()
    slot.refresh_from_db()
    assert shift.starts_at == new_start
    assert shift.ends_at == new_end
    assert shift.notes == 'Mobile edit saved'
    assert shift.confirmation_required is True
    assert slot.worker_id == worker_user.worker_profile.id
    assert slot.status == ShiftSlot.Status.CLAIMED


@pytest.mark.django_db
def test_admin_edit_preserves_claimed_worker_on_wiw_imported_shift(auth_admin, company, location, position, worker_user):
    starts = timezone.now() + timedelta(days=5, hours=2)
    worker = worker_user.worker_profile
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        worker=worker,
        starts_at=starts,
        ends_at=starts + timedelta(hours=6),
        required_count=1,
        status=Shift.Status.CONFIRMED,
        wiw_shift_id='qa-wiw-edit-claimed-1',
        schedule_groups=['service'],
    )
    slot = ShiftSlot.objects.get(shift=shift)
    assert slot.worker_id == worker.id
    assert slot.status == ShiftSlot.Status.CLAIMED
    assert slot.source == 'wiw'

    new_start = starts + timedelta(minutes=15)
    new_end = new_start + timedelta(hours=6)
    response = auth_admin.patch(
        f'/api/shifts/{shift.id}/cards/{slot.id}/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': new_start.isoformat(),
            'ends_at': new_end.isoformat(),
            'notes': 'WIW mobile edit saved',
            'confirmation_required': True,
            'schedule_groups': ['service'],
            'status': 'published',
            'apply_all': False,
        },
        format='json',
    )

    assert response.status_code == 200, response.data
    shift.refresh_from_db()
    slot.refresh_from_db()
    assert shift.starts_at == new_start
    assert shift.ends_at == new_end
    assert shift.worker_id == worker.id
    assert slot.worker_id == worker.id
    assert slot.status == ShiftSlot.Status.CLAIMED
    assert response.data['shift']['filled_count'] == 1
    assert response.data['shift']['open_count'] == 0


@pytest.mark.django_db
def test_admin_can_bulk_save_edit_for_multi_card_shift(auth_admin, company, location, position):
    starts = timezone.now() + timedelta(days=6)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=starts,
        ends_at=starts + timedelta(hours=5),
        required_count=2,
        status=Shift.Status.PUBLISHED,
    )
    ensure_slots(shift)
    slot = ShiftSlot.objects.filter(shift=shift).first()

    response = auth_admin.patch(
        f'/api/shifts/{shift.id}/cards/{slot.id}/',
        {
            'client': str(company.id),
            'location': str(location.id),
            'position': str(position.id),
            'starts_at': (starts + timedelta(minutes=15)).isoformat(),
            'ends_at': (starts + timedelta(hours=5, minutes=15)).isoformat(),
            'notes': 'Bulk edit saved',
            'confirmation_required': False,
            'schedule_groups': ['service'],
            'status': 'published',
            'apply_all': True,
        },
        format='json',
    )

    assert response.status_code == 200, response.data
    shift.refresh_from_db()
    assert shift.notes == 'Bulk edit saved'
    assert shift.required_count == 2
    assert ShiftSlot.objects.filter(shift=shift).exclude(status=ShiftSlot.Status.CANCELLED).count() == 2
