from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from core.models import Notification, Shift
from core.shift_slots import ShiftSlot


def _future_monday():
    today = timezone.localdate()
    days = (7 - today.weekday()) % 7
    return today + timedelta(days=days or 7)


def _aware(day, hour):
    return timezone.make_aware(
        datetime.combine(day, time(hour, 0)),
        timezone.get_current_timezone(),
    )


def _claim(slot, worker, source='qa'):
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = source
    slot.claimed_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])


@pytest.mark.django_db
def test_schedule_quality_detects_conflicts_from_native_slots(
    auth_admin,
    worker_user,
    company,
    location,
    position,
):
    day = _future_monday()
    first = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=_aware(day, 9),
        ends_at=_aware(day, 14),
        status=Shift.Status.PUBLISHED,
        required_count=1,
    )
    second = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=_aware(day, 13),
        ends_at=_aware(day, 18),
        status=Shift.Status.PUBLISHED,
        required_count=1,
    )
    _claim(first.slots.get(status=ShiftSlot.Status.OPEN), worker_user.worker_profile)
    _claim(second.slots.get(status=ShiftSlot.Status.OPEN), worker_user.worker_profile)

    response = auth_admin.get(
        '/api/operations/schedule-quality/',
        {
            'date_from': _aware(day, 0).isoformat(),
            'date_to': _aware(day + timedelta(days=1), 0).isoformat(),
        },
    )

    assert response.status_code == 200
    assert any(
        item['worker'] == str(worker_user.worker_profile.id)
        and {item['first_shift'], item['second_shift']} == {str(first.id), str(second.id)}
        for item in response.data['conflicts']
    )


@pytest.mark.django_db
def test_copy_week_preserves_multislot_assignments_and_open_capacity(
    auth_admin,
    worker_user,
    second_worker,
    company,
    location,
    position,
):
    source_day = _future_monday()
    target_day = source_day + timedelta(days=7)
    source = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=_aware(source_day, 10),
        ends_at=_aware(source_day, 15),
        break_minutes=30,
        status=Shift.Status.PUBLISHED,
        required_count=3,
        notes='Mehrpersonen-Schicht',
    )
    slots = list(source.slots.filter(status=ShiftSlot.Status.OPEN).order_by('created_at'))
    _claim(slots[0], worker_user.worker_profile)
    _claim(slots[1], second_worker)

    response = auth_admin.post(
        '/api/operations/copy-week/',
        {
            'source_start': source_day.isoformat(),
            'target_start': target_day.isoformat(),
        },
        format='json',
    )

    assert response.status_code == 201
    assert len(response.data['created']) == 1
    assert response.data['warnings'] == []

    clone = Shift.objects.get(pk=response.data['created'][0])
    assert clone.status == Shift.Status.DRAFT
    assert clone.required_count == 3
    assert clone.worker_id is None
    claimed = set(
        clone.slots.filter(status=ShiftSlot.Status.CLAIMED).values_list('worker_id', flat=True)
    )
    assert claimed == {worker_user.worker_profile.id, second_worker.id}
    assert clone.slots.filter(
        status=ShiftSlot.Status.OPEN,
        worker__isnull=True,
    ).count() == 1


@pytest.mark.django_db
def test_bulk_publish_notifies_every_native_assignee(
    auth_admin,
    worker_user,
    second_worker,
    company,
    location,
    position,
):
    day = _future_monday()
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=_aware(day, 16),
        ends_at=_aware(day, 21),
        status=Shift.Status.DRAFT,
        required_count=2,
    )
    slots = list(shift.slots.filter(status=ShiftSlot.Status.OPEN).order_by('created_at'))
    _claim(slots[0], worker_user.worker_profile)
    _claim(slots[1], second_worker)

    response = auth_admin.post(
        '/api/operations/bulk-publish/',
        {'ids': [str(shift.id)]},
        format='json',
    )

    assert response.status_code == 200
    assert response.data['published'] == 1
    shift.refresh_from_db()
    assert shift.status == Shift.Status.CONFIRMED
    kind = f'shift-published-{shift.id}'
    assert Notification.objects.filter(user=worker_user, kind=kind).exists()
    assert Notification.objects.filter(user=second_worker.user, kind=kind).exists()


@pytest.mark.django_db
def test_schedule_csv_expands_multislot_shift_into_worker_and_open_rows(
    auth_admin,
    worker_user,
    second_worker,
    company,
    location,
    position,
):
    day = _future_monday()
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=_aware(day, 11),
        ends_at=_aware(day, 17),
        status=Shift.Status.PUBLISHED,
        required_count=3,
    )
    slots = list(shift.slots.filter(status=ShiftSlot.Status.OPEN).order_by('created_at'))
    _claim(slots[0], worker_user.worker_profile)
    _claim(slots[1], second_worker)
    shift.refresh_from_db()
    assert shift.worker_id is None

    response = auth_admin.get(
        '/api/reports/schedule.csv',
        {'date_from': day.isoformat(), 'date_to': day.isoformat()},
    )

    assert response.status_code == 200
    body = response.content.decode('utf-8-sig')
    assert worker_user.get_full_name() in body
    assert second_worker.user.get_full_name() in body
    assert 'OpenShift' in body
    data_rows = [line for line in body.splitlines() if line.strip()][1:]
    assert len(data_rows) == 3
