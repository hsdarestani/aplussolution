from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Shift, ShiftSwapRequest, User, WorkerProfile
from core.scheduling_models import (
    PositionSkillTag,
    ScheduleGroup,
    ScheduleMembership,
    ScheduleTemplate,
    ScheduleTemplateItem,
    SchedulingPolicy,
    SkillTag,
    WorkerPositionQualification,
    WorkerSkillTag,
)
from core.shift_slots import ShiftSlot


def policy(**overrides):
    defaults = {
        'name': f'Policy-{timezone.now().timestamp()}',
        'qualification_mode': 'off',
        'schedule_membership_mode': 'off',
        'skill_tag_mode': 'off',
        'availability_mode': 'block',
        'time_off_mode': 'block',
        'rest_mode': 'off',
        'hours_mode': 'off',
        'days_mode': 'off',
    }
    defaults.update(overrides)
    return SchedulingPolicy.objects.create(**defaults)


def open_shift(company, location, position, start=None, hours=4, required_count=1):
    start = start or timezone.now() + timedelta(days=3)
    return Shift.objects.create(
        client=company,
        location=location,
        position=position,
        starts_at=start,
        ends_at=start + timedelta(hours=hours),
        required_count=required_count,
        status=Shift.Status.PUBLISHED,
        published_at=timezone.now(),
        is_open=True,
    )


@pytest.mark.django_db
def test_position_qualification_can_hard_block_claim(auth_worker, company, location, position):
    policy(qualification_mode='block')
    shift = open_shift(company, location, position)
    response = auth_worker.post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert response.status_code == 400
    assert 'Qualifikation' in str(response.data)


@pytest.mark.django_db
def test_position_qualification_allows_claim(auth_worker, worker_user, company, location, position):
    policy(qualification_mode='block')
    WorkerPositionQualification.objects.create(worker=worker_user.worker_profile, position=position)
    shift = open_shift(company, location, position)
    response = auth_worker.post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert response.status_code == 200


@pytest.mark.django_db
def test_required_verified_tag_is_enforced(auth_worker, worker_user, company, location, position):
    policy(skill_tag_mode='block')
    tag = SkillTag.objects.create(name='Hygieneschulung')
    PositionSkillTag.objects.create(position=position, tag=tag, required=True)
    shift = open_shift(company, location, position)
    denied = auth_worker.post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert denied.status_code == 400
    assert 'Hygieneschulung' in str(denied.data)
    WorkerSkillTag.objects.create(worker=worker_user.worker_profile, tag=tag, verified=True)
    allowed = auth_worker.post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_schedule_membership_can_be_required(auth_worker, worker_user, company, location, position):
    schedule = ScheduleGroup.objects.create(name='Frankfurt Service')
    schedule.locations.add(location)
    policy(schedule=schedule, schedule_membership_mode='block')
    shift = open_shift(company, location, position)
    denied = auth_worker.post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert denied.status_code == 400
    ScheduleMembership.objects.create(schedule=schedule, worker=worker_user.worker_profile)
    allowed = auth_worker.post(f'/api/shifts/{shift.id}/claim/', {}, format='json')
    assert allowed.status_code == 200


@pytest.mark.django_db
def test_minimum_rest_rule_blocks_short_turnaround(auth_worker, worker_user, company, location, position):
    policy(rest_mode='block', min_rest_hours=Decimal('11'))
    first = open_shift(company, location, position, start=timezone.now() + timedelta(days=1), hours=8)
    slot = first.slots.first()
    slot.worker = worker_user.worker_profile
    slot.status = ShiftSlot.Status.CLAIMED
    slot.save()
    first.status = Shift.Status.CONFIRMED
    first.save()
    second = open_shift(company, location, position, start=first.ends_at + timedelta(hours=6), hours=4)
    response = auth_worker.post(f'/api/shifts/{second.id}/claim/', {}, format='json')
    assert response.status_code == 400
    assert 'Mindestruhezeit' in str(response.data)


@pytest.mark.django_db
def test_weekly_hours_rule_blocks_projected_overtime(auth_worker, worker_user, company, location, position):
    policy(hours_mode='block', max_weekly_hours=Decimal('8'))
    monday = timezone.now() + timedelta(days=(7 - timezone.now().weekday()) % 7 + 7)
    monday = monday.replace(hour=8, minute=0, second=0, microsecond=0)
    existing = open_shift(company, location, position, start=monday, hours=6)
    slot = existing.slots.first()
    slot.worker = worker_user.worker_profile
    slot.status = ShiftSlot.Status.CLAIMED
    slot.save()
    existing.status = Shift.Status.CONFIRMED
    existing.save()
    candidate = open_shift(company, location, position, start=monday + timedelta(days=1), hours=4)
    response = auth_worker.post(f'/api/shifts/{candidate.id}/claim/', {}, format='json')
    assert response.status_code == 400
    assert 'Wochenstunden' in str(response.data)


@pytest.mark.django_db
def test_auto_assign_only_uses_eligible_workers(auth_admin, worker_user, second_worker, company, location, position):
    policy(qualification_mode='block')
    WorkerPositionQualification.objects.create(worker=second_worker, position=position)
    shift = open_shift(company, location, position, required_count=1)
    response = auth_admin.post('/api/scheduling/auto-assign/', {'shift': str(shift.id)}, format='json')
    assert response.status_code == 200
    assert response.data['assigned_count'] == 1
    claimed = ShiftSlot.objects.get(shift=shift, status=ShiftSlot.Status.CLAIMED)
    assert claimed.worker == second_worker
    assert claimed.source == 'auto_assign'


@pytest.mark.django_db
def test_manager_can_inspect_eligibility_reasons(auth_admin, worker_user, company, location, position):
    policy(qualification_mode='block')
    shift = open_shift(company, location, position)
    response = auth_admin.get(f'/api/scheduling/eligibility/?shift={shift.id}')
    assert response.status_code == 200
    row = next(item for item in response.data['workers'] if item['worker'] == str(worker_user.worker_profile.id))
    assert row['eligible'] is False
    assert any(item['code'] == 'position_qualification' for item in row['blockers'])


@pytest.mark.django_db
def test_multi_slot_swap_uses_slot_and_rules(auth_admin, worker_user, second_worker, company, location, position):
    policy(qualification_mode='block')
    WorkerPositionQualification.objects.create(worker=worker_user.worker_profile, position=position)
    WorkerPositionQualification.objects.create(worker=second_worker, position=position)
    shift = open_shift(company, location, position, required_count=2)
    owner_slot = shift.slots.first()
    owner_slot.worker = worker_user.worker_profile
    owner_slot.status = ShiftSlot.Status.CLAIMED
    owner_slot.save()
    client = APIClient(); client.force_authenticate(worker_user)
    requested = client.post('/api/operations/swaps/', {'shift': str(shift.id), 'offered_to': str(second_worker.id)}, format='json')
    assert requested.status_code == 201
    approved = auth_admin.post(f'/api/operations/swaps/{requested.data["id"]}/decide/', {'status': 'approved'}, format='json')
    assert approved.status_code == 200
    owner_slot.refresh_from_db()
    assert owner_slot.worker == second_worker
    assert ShiftSwapRequest.objects.get(pk=requested.data['id']).status == 'approved'


@pytest.mark.django_db
def test_schedule_template_applies_week_without_duplicates(auth_admin, company, location, position):
    template = ScheduleTemplate.objects.create(name='Standardwoche')
    ScheduleTemplateItem.objects.create(
        template=template,
        weekday=0,
        start_time=time(8, 0),
        end_time=time(16, 0),
        client=company,
        location=location,
        position=position,
        required_count=3,
        break_minutes=30,
    )
    target = (timezone.localdate() + timedelta(days=14)).isoformat()
    first = auth_admin.post(f'/api/scheduling/templates/{template.id}/apply/', {'target_week_start': target}, format='json')
    assert first.status_code == 201
    assert len(first.data['created']) == 1
    second = auth_admin.post(f'/api/scheduling/templates/{template.id}/apply/', {'target_week_start': target}, format='json')
    assert second.status_code == 201
    assert len(second.data['created']) == 0
    assert len(second.data['skipped']) == 1
