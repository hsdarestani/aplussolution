from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Availability, Notification, Shift, ShiftSwapRequest, TimeEntry


@pytest.mark.django_db
def test_shift_overlap_is_rejected(auth_admin, shift, worker_user, company, location, position):
    response = auth_admin.post('/api/shifts/', {
        'client': str(company.id), 'location': str(location.id), 'position': str(position.id),
        'worker': str(worker_user.worker_profile.id),
        'starts_at': (shift.starts_at + timedelta(minutes=30)).isoformat(),
        'ends_at': (shift.ends_at + timedelta(hours=1)).isoformat(),
    }, format='json')
    assert response.status_code == 400
    assert 'bereits eine Schicht' in str(response.data)


@pytest.mark.django_db
def test_unavailability_blocks_assignment(auth_admin, worker_user, company, location, position):
    start = timezone.now() + timedelta(days=1)
    Availability.objects.create(worker=worker_user.worker_profile, starts_at=start, ends_at=start + timedelta(hours=8), available=False)
    response = auth_admin.post('/api/shifts/', {
        'client': str(company.id), 'location': str(location.id), 'position': str(position.id),
        'worker': str(worker_user.worker_profile.id), 'starts_at': start.isoformat(),
        'ends_at': (start + timedelta(hours=4)).isoformat(),
    }, format='json')
    assert response.status_code == 400
    assert 'nicht verfügbar' in str(response.data)


@pytest.mark.django_db
def test_worker_claims_open_shift(auth_worker, worker_user, company, location, position):
    start = timezone.now() + timedelta(days=2)
    open_shift = Shift.objects.create(client=company, location=location, position=position, starts_at=start, ends_at=start + timedelta(hours=4), status='published', is_open=True)
    response = auth_worker.post(f'/api/shifts/{open_shift.id}/claim/', {}, format='json')
    assert response.status_code == 200
    open_shift.refresh_from_db()
    assert open_shift.worker == worker_user.worker_profile
    assert open_shift.is_open is False


@pytest.mark.django_db
def test_geofence_clock_in_and_out(auth_worker, worker_user, shift):
    shift.starts_at = timezone.now() - timedelta(minutes=10)
    shift.ends_at = timezone.now() + timedelta(hours=4)
    shift.save()
    outside = auth_worker.post('/api/time-entries/clock_in/', {'shift': str(shift.id), 'lat': 51, 'lng': 9}, format='json')
    assert outside.status_code == 400
    inside = auth_worker.post('/api/time-entries/clock_in/', {'shift': str(shift.id), 'lat': 50.1101, 'lng': 8.6801}, format='json')
    assert inside.status_code == 201
    out = auth_worker.post('/api/time-entries/clock_out/', {'lat': 50.1101, 'lng': 8.6801}, format='json')
    assert out.status_code == 200
    assert TimeEntry.objects.get().clock_out is not None


@pytest.mark.django_db
def test_copy_week_and_bulk_publish(auth_admin, shift):
    source = shift.starts_at.date().isoformat()
    target = (shift.starts_at.date() + timedelta(days=7)).isoformat()
    response = auth_admin.post('/api/operations/copy-week/', {'source_start': source, 'target_start': target}, format='json')
    assert response.status_code == 201
    copied = Shift.objects.get(pk=response.data['created'][0])
    assert copied.status == Shift.Status.DRAFT
    response = auth_admin.post('/api/operations/bulk-publish/', {'ids': [str(copied.id)]}, format='json')
    assert response.status_code == 200
    copied.refresh_from_db()
    assert copied.status == Shift.Status.PUBLISHED


@pytest.mark.django_db
def test_shift_swap_requires_target_and_transfers_shift(auth_admin, worker_user, second_worker, shift):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(worker_user)
    request = client.post('/api/operations/swaps/', {'shift': str(shift.id), 'note': 'Bitte übernehmen'}, format='json')
    assert request.status_code == 201
    swap_id = request.data['id']
    no_target = auth_admin.post(f'/api/operations/swaps/{swap_id}/decide/', {'status': 'approved'}, format='json')
    assert no_target.status_code == 400
    approved = auth_admin.post(f'/api/operations/swaps/{swap_id}/decide/', {'status': 'approved', 'offered_to': str(second_worker.id)}, format='json')
    assert approved.status_code == 200
    shift.refresh_from_db()
    assert shift.worker == second_worker
    assert ShiftSwapRequest.objects.get(pk=swap_id).status == 'approved'
    assert Notification.objects.filter(user=worker_user, kind='shift-swap-decision').exists()
