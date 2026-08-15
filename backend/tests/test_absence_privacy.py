from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.absence_models import CoverageOffer, ShiftAbsenceCase
from core.models import Shift
from core.shift_service import refresh_shift_state
from core.shift_slots import ShiftSlot


pytestmark = pytest.mark.django_db


def auth(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def assigned_shift(company, location, position, worker):
    start = timezone.now() + timedelta(hours=6)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=5),
        status=Shift.Status.CONFIRMED,
    )
    slot = shift.slots.first()
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'privacy_test'
    slot.claimed_at = timezone.now()
    slot.save()
    refresh_shift_state(shift)
    return shift, slot


def test_absent_worker_cannot_see_internal_offer_targets_or_manager_note(auth_admin, admin_user, worker_user, second_worker, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile)
    reported = auth_admin.post(
        '/api/operations/callouts/report/',
        {'shift': str(shift.id), 'slot': str(slot.id), 'worker': str(worker_user.worker_profile.id), 'kind': 'sick', 'note': 'private reason'},
        format='json',
    )
    case = ShiftAbsenceCase.objects.get(pk=reported.data['id'])
    case.manager_note = 'internal dispatcher note'
    case.save(update_fields=['manager_note', 'updated_at'])
    CoverageOffer.objects.create(case=case, worker=second_worker, offered_by=admin_user, expires_at=timezone.now() + timedelta(hours=1))

    response = auth(worker_user).get(f'/api/absence-cases/{case.id}/')
    assert response.status_code == 200
    assert response.data['manager_note'] == ''
    assert response.data['offers'] == []
    assert response.data['open_offer_count'] == 0


def test_replacement_offer_payload_does_not_expose_absent_identity_or_reason(auth_admin, worker_user, second_worker, company, location, position):
    shift, slot = assigned_shift(company, location, position, worker_user.worker_profile)
    reported = auth_admin.post(
        '/api/operations/callouts/report/',
        {'shift': str(shift.id), 'slot': str(slot.id), 'worker': str(worker_user.worker_profile.id), 'kind': 'sick', 'note': 'medical detail'},
        format='json',
    )
    offered = auth_admin.post(
        f"/api/absence-cases/{reported.data['id']}/offer/",
        {'workers': [str(second_worker.id)], 'expires_in_hours': 2},
        format='json',
    )
    assert offered.status_code == 201
    offer_id = offered.data[0]['id']

    list_response = auth(second_worker.user).get('/api/coverage-offers/?status=pending')
    assert list_response.status_code == 200
    rows = list_response.data.get('results', list_response.data)
    assert len(rows) == 1
    serialized = rows[0]
    assert 'absent_worker_name' not in serialized
    assert 'reason_note' not in serialized

    accepted = auth(second_worker.user).post(f'/api/coverage-offers/{offer_id}/respond/', {'status': 'accepted'}, format='json')
    assert accepted.status_code == 200
    assert set(accepted.data['case']) == {'id', 'shift', 'status', 'coverage_strategy'}
