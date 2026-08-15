from datetime import timedelta

import pytest
from django.utils import timezone

from core.absence_models import CoverageOffer, ShiftAbsenceCase
from core.absence_service import report_absence, resolve_uncovered
from core.models import Shift
from core.shift_service import refresh_shift_state
from core.shift_slots import ShiftSlot
from core.tasks import expire_coverage_offers


pytestmark = pytest.mark.django_db


def make_case(worker_user, company, location, position, manager_user):
    start = timezone.now() + timedelta(hours=4)
    shift = Shift.objects.create(client=company, location=location, position=position, starts_at=start, ends_at=start + timedelta(hours=5), status=Shift.Status.CONFIRMED)
    slot = shift.slots.first()
    slot.worker = worker_user.worker_profile
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'test'
    slot.claimed_at = timezone.now()
    slot.save()
    refresh_shift_state(shift)
    case = report_absence(shift=shift, absent_worker=worker_user.worker_profile, reported_by=manager_user, kind='sick', slot_id=slot.id)
    return case, shift, slot


def test_expired_offers_reopen_case(worker_user, second_worker, company, location, position, manager_user):
    case, _, _ = make_case(worker_user, company, location, position, manager_user)
    case.status = ShiftAbsenceCase.Status.OFFERED
    case.coverage_strategy = ShiftAbsenceCase.CoverageStrategy.TARGETED
    case.save()
    CoverageOffer.objects.create(case=case, worker=second_worker, offered_by=manager_user, expires_at=timezone.now() - timedelta(minutes=1))
    result = expire_coverage_offers()
    case.refresh_from_db()
    offer = case.offers.get()
    assert result == {'expired': 1, 'reopened_cases': 1}
    assert offer.status == CoverageOffer.Status.EXPIRED
    assert case.status == ShiftAbsenceCase.Status.COVERAGE_PENDING


def test_resolve_uncovered_removes_absent_worker_from_staffing_slot(worker_user, company, location, position, manager_user):
    case, shift, slot = make_case(worker_user, company, location, position, manager_user)
    resolve_uncovered(case.id, manager_user, 'Betrieb arbeitet unterbesetzt weiter')
    case.refresh_from_db(); slot.refresh_from_db(); shift.refresh_from_db()
    assert case.status == ShiftAbsenceCase.Status.RESOLVED_UNCOVERED
    assert slot.worker_id is None
    assert slot.status == ShiftSlot.Status.OPEN
    assert shift.status == Shift.Status.PUBLISHED
