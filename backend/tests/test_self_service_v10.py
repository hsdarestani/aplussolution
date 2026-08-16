from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Availability, Shift
from core.scheduling_rules import evaluate_worker_for_shift, eligible_workers_for_shift
from core.self_service_models import (
    AvailabilityPreferenceSeries,
    AvailabilitySeriesOccurrence,
    OpenShiftPolicy,
    OpenShiftRequest,
    SelfServiceSettings,
    ShiftCoverageRequest,
    TimeOffType,
    UserSelfServicePreference,
)
from core.self_service_service import (
    accept_coverage_request,
    coworker_directory_for,
    create_coverage_request,
    review_coverage_request,
    team_schedule_for,
    worker_can_access_open_shift,
)
from core.shift_service import ensure_slots, refresh_shift_state
from core.shift_slots import ShiftSlot

pytestmark = pytest.mark.django_db


def _open_shift(company, location, position, *, days=5, hours=6):
    start = (timezone.now() + timedelta(days=days)).replace(minute=0, second=0, microsecond=0)
    shift = Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=hours),
        status=Shift.Status.PUBLISHED,
        published_at=timezone.now(),
        required_count=1,
        is_open=True,
    )
    ensure_slots(shift)
    return shift


def _claim_for(shift, worker, source='test'):
    slot = shift.slots.filter(status=ShiftSlot.Status.OPEN).first()
    assert slot is not None
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = source
    slot.claimed_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    refresh_shift_state(shift)
    return slot


def test_recurring_preferences_materialize_and_affect_scheduler(worker_user, second_worker, company, location, position):
    shift = _open_shift(company, location, position, days=14)
    day = timezone.localtime(shift.starts_at).date()

    AvailabilityPreferenceSeries.objects.create(
        worker=second_worker,
        kind=AvailabilityPreferenceSeries.Kind.PREFERRED,
        starts_on=day,
        ends_on=day,
        recurrence=AvailabilityPreferenceSeries.Recurrence.ONCE,
        all_day=True,
        created_by=second_worker.user,
    )
    preferred = evaluate_worker_for_shift(second_worker, shift)
    baseline = evaluate_worker_for_shift(worker_user.worker_profile, shift)
    assert preferred['eligible'] is True
    assert preferred['preferred_availability'] is True
    assert preferred['preference_bonus'] == 150
    assert preferred['score'] > baseline['score']
    assert eligible_workers_for_shift(shift)[0]['worker'] == str(second_worker.id)

    unavailable = AvailabilityPreferenceSeries.objects.create(
        worker=second_worker,
        kind=AvailabilityPreferenceSeries.Kind.UNAVAILABLE,
        starts_on=day,
        ends_on=day,
        recurrence=AvailabilityPreferenceSeries.Recurrence.ONCE,
        all_day=True,
        note='Nicht verfügbar',
        created_by=second_worker.user,
    )
    assert AvailabilitySeriesOccurrence.objects.filter(series=unavailable).count() == 1
    assert Availability.objects.filter(worker=second_worker, available=False).count() == 1
    blocked = evaluate_worker_for_shift(second_worker, shift)
    assert blocked['eligible'] is False
    assert any(item['code'] == 'unavailable' for item in blocked['blockers'])


def test_worker_availability_api_owns_series_and_archive_clears_legacy(auth_worker, worker_user):
    start = timezone.localdate() + timedelta(days=7)
    end = start + timedelta(days=14)
    response = auth_worker.post('/api/self-service/availability/', {
        'kind': 'unavailable',
        'starts_on': start.isoformat(),
        'ends_on': end.isoformat(),
        'all_day': True,
        'recurrence': 'weekly',
        'weekdays': [start.weekday()],
        'note': 'Jeden Montag blockiert',
    }, format='json')
    assert response.status_code == 201, response.data
    series = AvailabilityPreferenceSeries.objects.get(pk=response.data['id'])
    assert series.worker_id == worker_user.worker_profile.id
    assert AvailabilitySeriesOccurrence.objects.filter(series=series).count() == 3
    assert Availability.objects.filter(worker=worker_user.worker_profile, available=False).count() == 3

    deleted = auth_worker.delete(f'/api/self-service/availability/{series.id}/')
    assert deleted.status_code == 204
    series.refresh_from_db()
    assert series.active is False
    assert AvailabilitySeriesOccurrence.objects.filter(series=series).count() == 0
    assert Availability.objects.filter(worker=worker_user.worker_profile, available=False).count() == 0


def test_open_shift_bid_requires_manager_approval(auth_worker, auth_admin, worker_user, company, location, position):
    shift = _open_shift(company, location, position)
    OpenShiftPolicy.objects.create(shift=shift, require_approval=True)

    response = auth_worker.post('/api/self-service/open-shift-requests/', {'shift': str(shift.id), 'note': 'Kann übernehmen'}, format='json')
    assert response.status_code == 202, response.data
    row = OpenShiftRequest.objects.get(pk=response.data['id'])
    assert row.status == OpenShiftRequest.Status.PENDING_APPROVAL
    assert shift.slots.filter(status=ShiftSlot.Status.OPEN).count() == 1

    approved = auth_admin.post(f'/api/self-service/open-shift-requests/{row.id}/decide/', {'approve': True}, format='json')
    assert approved.status_code == 200, approved.data
    row.refresh_from_db()
    assert row.status == OpenShiftRequest.Status.ACCEPTED
    assert shift.slots.filter(worker=worker_user.worker_profile, status=ShiftSlot.Status.CLAIMED).exists()


def test_targeted_open_shift_rejects_worker_outside_audience(worker_user, second_worker, company, location, position):
    shift = _open_shift(company, location, position)
    policy = OpenShiftPolicy.objects.create(
        shift=shift,
        require_approval=True,
        audience_mode=OpenShiftPolicy.AudienceMode.SELECTED,
    )
    policy.selected_workers.add(second_worker)
    allowed, reason = worker_can_access_open_shift(worker_user.worker_profile, shift)
    assert allowed is False
    assert 'nicht angeboten' in reason
    allowed_second, _ = worker_can_access_open_shift(second_worker, shift)
    assert allowed_second is True


def test_drop_review_and_accept_transfers_slot(worker_user, second_worker, admin_user, company, location, position):
    shift = _open_shift(company, location, position)
    slot = _claim_for(shift, worker_user.worker_profile)
    settings = SelfServiceSettings.load()
    settings.require_manager_review_swaps_drops = True
    settings.save(update_fields=['require_manager_review_swaps_drops', 'updated_at'])

    request = create_coverage_request(
        worker_user.worker_profile,
        shift=shift,
        kind=ShiftCoverageRequest.Kind.DROP,
        offered_to=second_worker,
        note='Bitte übernehmen',
    )
    assert request.status == ShiftCoverageRequest.Status.PENDING_REVIEW
    review_coverage_request(request, manager=admin_user, approve=True)
    request.refresh_from_db()
    assert request.status == ShiftCoverageRequest.Status.PENDING_ACCEPTANCE

    accept_coverage_request(request.id, recipient=second_worker)
    request.refresh_from_db(); slot.refresh_from_db()
    assert request.status == ShiftCoverageRequest.Status.ACCEPTED
    assert slot.worker_id == second_worker.id
    assert slot.source == 'shift_drop'


def test_swap_acceptance_exchanges_two_locked_slots(worker_user, second_worker, admin_user, company, location, position):
    first = _open_shift(company, location, position, days=5)
    second = _open_shift(company, location, position, days=8)
    first_slot = _claim_for(first, worker_user.worker_profile)
    second_slot = _claim_for(second, second_worker)

    request = create_coverage_request(
        worker_user.worker_profile,
        shift=first,
        kind=ShiftCoverageRequest.Kind.SWAP,
        offered_to=second_worker,
        note='Tausch?',
    )
    review_coverage_request(request, manager=admin_user, approve=True)
    accept_coverage_request(request.id, recipient=second_worker, offered_shift=second)

    first_slot.refresh_from_db(); second_slot.refresh_from_db(); request.refresh_from_db()
    assert request.status == ShiftCoverageRequest.Status.ACCEPTED
    assert request.offered_shift_id == second.id
    assert first_slot.worker_id == second_worker.id
    assert second_slot.worker_id == worker_user.worker_profile.id
    assert first_slot.source == second_slot.source == 'shift_swap'


def test_privacy_controls_coworkers_and_team_schedule(worker_user, second_worker, company, location, position):
    shift = _open_shift(company, location, position)
    _claim_for(shift, second_worker)
    settings = SelfServiceSettings.load()
    settings.team_schedule_visibility = SelfServiceSettings.TeamScheduleVisibility.ALL
    settings.global_user_privacy = False
    settings.save(update_fields=['team_schedule_visibility', 'global_user_privacy', 'updated_at'])
    UserSelfServicePreference.objects.create(user=second_worker.user, hide_contact_info=True)

    directory = coworker_directory_for(worker_user)
    second = next(row for row in directory['workers'] if row['id'] == str(second_worker.id))
    assert second['contact_hidden'] is True
    assert second['email'] is None

    rows = team_schedule_for(
        worker_user,
        starts_at=shift.starts_at - timedelta(hours=1),
        ends_at=shift.ends_at + timedelta(hours=1),
    )
    assert len(rows) == 1
    assert rows[0]['workers'] == ['Lukas Schmidt']

    settings.global_user_privacy = True
    settings.save(update_fields=['global_user_privacy', 'updated_at'])
    assert coworker_directory_for(worker_user)['visible'] is False
    assert team_schedule_for(worker_user, starts_at=shift.starts_at, ends_at=shift.ends_at) == []


def test_detailed_time_off_enforces_notice_paid_limit_and_partial_day(auth_worker):
    settings = SelfServiceSettings.load()
    settings.time_off_notice_days = 2
    settings.time_off_max_paid_hours_per_day = '8.00'
    settings.save(update_fields=['time_off_notice_days', 'time_off_max_paid_hours_per_day', 'updated_at'])
    TimeOffType.objects.create(
        code='holiday-test',
        name='Urlaub Test',
        kind=TimeOffType.Kind.HOLIDAY,
        allow_paid=True,
        allow_unpaid=True,
        active=True,
    )
    too_soon = timezone.localdate() + timedelta(days=1)
    response = auth_worker.post('/api/self-service/time-off/', {
        'type': 'holiday-test',
        'starts_on': too_soon.isoformat(),
        'ends_on': too_soon.isoformat(),
        'all_day': True,
        'paid': False,
    }, format='json')
    assert response.status_code == 400

    day = timezone.localdate() + timedelta(days=4)
    overpaid = auth_worker.post('/api/self-service/time-off/', {
        'type': 'holiday-test',
        'starts_on': day.isoformat(),
        'ends_on': day.isoformat(),
        'all_day': True,
        'paid': True,
        'paid_hours': '9.00',
    }, format='json')
    assert overpaid.status_code == 400

    partial = auth_worker.post('/api/self-service/time-off/', {
        'type': 'holiday-test',
        'starts_on': day.isoformat(),
        'ends_on': day.isoformat(),
        'all_day': False,
        'start_time': '09:00',
        'end_time': '13:00',
        'paid': True,
        'paid_hours': '4.00',
        'reason': 'Termin',
    }, format='json')
    assert partial.status_code == 201, partial.data
    assert partial.data['all_day'] is False
    assert partial.data['paid'] is True
    assert str(partial.data['paid_hours']) == '4.00'
