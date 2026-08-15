from datetime import timedelta

import pytest
from rest_framework.test import APIClient
from django.utils import timezone

from core.absence_models import CoverageOffer, ShiftAbsenceCase
from core.models import Availability, Shift, TimeOffRequest, User, WorkerProfile
from core.shift_service import refresh_shift_state
from core.shift_slots import ShiftSlot


pytestmark = pytest.mark.django_db


def assigned_shift(company, location, position, worker, *, starts_in_hours=4, required_count=1):
    start = timezone.now() + timedelta(hours=starts_in_hours)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=6),
        required_count=required_count,
        status=Shift.Status.CONFIRMED,
    )
    slot = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at').first()
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'test'
    slot.claimed_at = timezone.now()
    slot.save()
    refresh_shift_state(shift)
    return shift, slot


def auth_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def third_worker():
    user = User.objects.create_user(
        'worker3@example.com', 'StrongPass123!', first_name='Nina', last_name='Keller', role=User.Role.WORKER, is_onboarded=True
    )
    return WorkerProfile.objects.create(
        user=user, employee_number='MA-003', employment_type='teilzeit', monthly_hours='80', tariff_hourly_rate='15.50'
    )


def test_worker_reports_short_notice_callout_and_duplicate_is_blocked(auth_worker, worker_user, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile, starts_in_hours=4)
    response = auth_worker.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'kind': 'sick', 'note': 'Fieber'}, format='json')
    assert response.status_code == 201
    assert response.data['status'] == 'coverage_pending'
    assert response.data['short_notice'] is True
    assert response.data['kind'] == 'sick'
    duplicate = auth_worker.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'kind': 'sick'}, format='json')
    assert duplicate.status_code == 409
    assert ShiftAbsenceCase.objects.filter(slot=slot).count() == 1


def test_worker_cannot_report_another_workers_assignment(auth_worker, worker_user, second_worker, company, location, position):
    shift, slot = assigned_shift(company, location, position, second_worker)
    response = auth_worker.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'kind': 'personal'}, format='json')
    assert response.status_code == 400
    assert ShiftAbsenceCase.objects.count() == 0


def test_manager_candidate_list_excludes_absent_worker(auth_admin, worker_user, second_worker, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile)
    reported = auth_admin.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'worker': str(worker_user.worker_profile.id), 'kind': 'emergency'}, format='json')
    assert reported.status_code == 201
    response = auth_admin.get(f"/api/absence-cases/{reported.data['id']}/candidates/")
    assert response.status_code == 200
    ids = {row['worker'] for row in response.data['workers']}
    assert str(worker_user.worker_profile.id) not in ids
    assert str(second_worker.id) in ids


def test_move_to_open_then_worker_claim_resolves_case(auth_admin, worker_user, second_worker, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile)
    case_response = auth_admin.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'worker': str(worker_user.worker_profile.id), 'kind': 'sick'}, format='json')
    case_id = case_response.data['id']
    opened = auth_admin.post(f'/api/absence-cases/{case_id}/move-to-open/', {}, format='json')
    assert opened.status_code == 200
    slot.refresh_from_db(); shift.refresh_from_db()
    assert slot.status == ShiftSlot.Status.OPEN
    assert slot.worker_id is None
    assert shift.status == Shift.Status.PUBLISHED
    claimed = auth_for(second_worker.user).post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert claimed.status_code == 200
    case = ShiftAbsenceCase.objects.get(pk=case_id)
    assert case.status == ShiftAbsenceCase.Status.COVERED
    assert case.replacement_worker_id == second_worker.id


def test_targeted_offer_acceptance_is_atomic_and_cancels_other_offers(auth_admin, worker_user, second_worker, company, location, position):
    third = third_worker()
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile)
    case_response = auth_admin.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'worker': str(worker_user.worker_profile.id), 'kind': 'emergency'}, format='json')
    case_id = case_response.data['id']
    offered = auth_admin.post(f'/api/absence-cases/{case_id}/offer/', {'workers': [str(second_worker.id), str(third.id)], 'expires_in_hours': 8}, format='json')
    assert offered.status_code == 201
    assert len(offered.data) == 2
    second_offer = CoverageOffer.objects.get(case_id=case_id, worker=second_worker)
    third_offer = CoverageOffer.objects.get(case_id=case_id, worker=third)
    accepted = auth_for(second_worker.user).post(f'/api/coverage-offers/{second_offer.id}/respond/', {'status': 'accepted'}, format='json')
    assert accepted.status_code == 200
    third_offer.refresh_from_db()
    assert third_offer.status == CoverageOffer.Status.CANCELLED
    too_late = auth_for(third.user).post(f'/api/coverage-offers/{third_offer.id}/respond/', {'status': 'accepted'}, format='json')
    assert too_late.status_code == 409
    slot.refresh_from_db()
    assert slot.worker_id == second_worker.id


def test_direct_replacement_rechecks_unavailability(auth_admin, worker_user, second_worker, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile)
    Availability.objects.create(worker=second_worker, starts_at=shift.starts_at - timedelta(minutes=5), ends_at=shift.ends_at + timedelta(minutes=5), available=False)
    case_response = auth_admin.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'worker': str(worker_user.worker_profile.id), 'kind': 'sick'}, format='json')
    response = auth_admin.post(f"/api/absence-cases/{case_response.data['id']}/replace/", {'worker': str(second_worker.id)}, format='json')
    assert response.status_code == 400
    slot.refresh_from_db()
    assert slot.worker_id == worker_user.worker_profile.id


def test_approved_time_off_creates_cases_only_for_impacted_assignments(manager_user, worker_user, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile, starts_in_hours=48)
    request = TimeOffRequest.objects.create(
        worker=worker_user.worker_profile,
        starts_on=timezone.localdate(shift.starts_at),
        ends_on=timezone.localdate(shift.starts_at),
        reason='Urlaub',
    )
    request.status = TimeOffRequest.Status.APPROVED
    request.decided_by = manager_user
    request.save()
    case = ShiftAbsenceCase.objects.get(slot=slot)
    assert case.source == ShiftAbsenceCase.Source.TIME_OFF
    assert case.kind == ShiftAbsenceCase.Kind.APPROVED_TIME_OFF
    assert case.time_off_request_id == request.id
    request.save()
    assert ShiftAbsenceCase.objects.filter(slot=slot).count() == 1


def test_manager_can_record_no_show(auth_admin, worker_user, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile, starts_in_hours=-1)
    response = auth_admin.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'worker': str(worker_user.worker_profile.id), 'kind': 'no_show', 'note': 'Nicht erschienen'}, format='json')
    assert response.status_code == 201
    assert response.data['kind'] == 'no_show'
    assert response.data['source'] == 'manager'
    assert response.data['short_notice'] is True


def test_client_cannot_read_sensitive_absence_cases(auth_admin, auth_client, worker_user, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile)
    response = auth_admin.post('/api/operations/callouts/report/', {'shift': str(shift.id), 'slot': str(slot.id), 'worker': str(worker_user.worker_profile.id), 'kind': 'sick', 'note': 'Sensitive medical note'}, format='json')
    assert response.status_code == 201
    client_response = auth_client.get('/api/absence-cases/')
    assert client_response.status_code == 200
    rows = client_response.data.get('results', client_response.data)
    assert rows == []
