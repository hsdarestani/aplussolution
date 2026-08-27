from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Shift
from core.shift_rules import automatic_break_minutes


@pytest.mark.parametrize(('hours', 'minutes'), [(5.99, 0), (6, 30), (8.99, 30), (9, 45), (10.99, 45), (11, 60), (13, 60)])
def test_automatic_break_thresholds(hours, minutes):
    start = timezone.now()
    end = start + timedelta(hours=hours)
    assert automatic_break_minutes(start, end) == minutes


@pytest.mark.django_db
def test_native_shift_api_overrides_manual_break_with_automatic_rule(auth_admin, company, location, position):
    start = timezone.now() + timedelta(days=2)
    response = auth_admin.post('/api/shifts/', {
        'client': str(company.id),
        'location': str(location.id),
        'position': str(position.id),
        'starts_at': start.isoformat(),
        'ends_at': (start + timedelta(hours=9)).isoformat(),
        'required_count': 1,
        'break_minutes': 0,
        'status': 'draft',
    }, format='json')
    assert response.status_code == 201, response.data
    assert response.data['break_minutes'] == 45
    assert Shift.objects.get(pk=response.data['id']).break_minutes == 45


@pytest.mark.django_db
def test_worker_open_shifts_respect_client_and_zeitplan_preferences(
    auth_worker, worker_user, company, location, position
):
    other_company = company.__class__.objects.create(name='Anderer Kunde', customer_number='KD-VIS-2')
    other_location = location.__class__.objects.create(client=other_company, name='Anderer Standort', address='Test 2')
    start = timezone.now() + timedelta(days=3)

    allowed = Shift.objects.create(
        client=company, location=location, position=position,
        starts_at=start, ends_at=start + timedelta(hours=7), status=Shift.Status.PUBLISHED,
        required_count=1, schedule_groups=['service'],
    )
    blocked_group = Shift.objects.create(
        client=company, location=location, position=position,
        starts_at=start + timedelta(hours=8), ends_at=start + timedelta(hours=15), status=Shift.Status.PUBLISHED,
        required_count=1, schedule_groups=['housekeeping'],
    )
    blocked_client = Shift.objects.create(
        client=other_company, location=other_location, position=position,
        starts_at=start + timedelta(days=1), ends_at=start + timedelta(days=1, hours=7), status=Shift.Status.PUBLISHED,
        required_count=1, schedule_groups=['service'],
    )

    # Native ShiftSlot capacity is created by the Shift post-save signal.
    assert allowed.slots.filter(status='open').exists()
    assert blocked_group.slots.filter(status='open').exists()
    assert blocked_client.slots.filter(status='open').exists()

    worker = worker_user.worker_profile
    worker.open_shift_client_ids = [str(company.id)]
    worker.schedule_groups = ['service']
    worker.save(update_fields=['open_shift_client_ids', 'schedule_groups'])

    response = auth_worker.get('/api/shifts/available/')
    assert response.status_code == 200, response.data
    rows = response.data.get('results', response.data)
    ids = {str(row['id']) for row in rows}
    assert str(allowed.id) in ids
    assert str(blocked_group.id) not in ids
    assert str(blocked_client.id) not in ids
