from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Availability, Shift, TimeOffRequest, WorkerProfile
from .scheduling_models import (
    PositionSkillTag,
    ScheduleGroup,
    ScheduleMembership,
    ScheduleTemplate,
    SchedulingPolicy,
    WorkerPositionQualification,
    WorkerSkillTag,
)
from .shift_slots import ShiftSlot


DEFAULT_POLICY = SimpleNamespace(
    id=None,
    name='A+ Standard',
    schedule_id=None,
    location_id=None,
    position_id=None,
    min_rest_hours=Decimal('11'),
    max_days_per_week=6,
    max_consecutive_days=6,
    max_weekly_hours=Decimal('48'),
    qualification_mode='warn',
    schedule_membership_mode='off',
    skill_tag_mode='warn',
    availability_mode='block',
    time_off_mode='block',
    rest_mode='warn',
    hours_mode='warn',
    days_mode='warn',
)


def _local_date(value):
    return timezone.localtime(value).date()


def _week_bounds(value):
    local = timezone.localtime(value)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday, monday + timedelta(days=7)


def _worked_minutes(shift):
    return max(0, int((shift.ends_at - shift.starts_at).total_seconds() // 60) - int(shift.break_minutes or 0))


def _assignment_queryset(worker, start, end, exclude_shift_id=None):
    qs = Shift.objects.filter(
        Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=worker),
        starts_at__lt=end,
        ends_at__gt=start,
    ).exclude(status=Shift.Status.CANCELLED).distinct()
    if exclude_shift_id:
        qs = qs.exclude(pk=exclude_shift_id)
    return qs


def _scope_score(policy, shift):
    score = 0
    if policy.schedule_id:
        score += 1
        if policy.schedule.locations.filter(pk=shift.location_id).exists():
            score += 2
        else:
            return -1
    if policy.location_id:
        if policy.location_id != shift.location_id:
            return -1
        score += 4
    if policy.position_id:
        if policy.position_id != shift.position_id:
            return -1
        score += 8
    return score


def policy_for_shift(shift):
    policies = SchedulingPolicy.objects.filter(active=True).select_related('schedule', 'location', 'position').prefetch_related('schedule__locations')
    ranked = [(score, policy) for policy in policies if (score := _scope_score(policy, shift)) >= 0]
    if not ranked:
        return DEFAULT_POLICY
    ranked.sort(key=lambda row: (row[0], row[1].updated_at), reverse=True)
    return ranked[0][1]


def _issue(mode, code, message, **meta):
    if mode == SchedulingPolicy.Enforcement.OFF:
        return None
    return {
        'code': code,
        'severity': 'block' if mode == SchedulingPolicy.Enforcement.BLOCK else 'warn',
        'message': message,
        'meta': meta,
    }


def _qualification_issue(worker, shift, policy):
    if policy.qualification_mode == SchedulingPolicy.Enforcement.OFF:
        return None
    day = _local_date(shift.starts_at)
    qualified = WorkerPositionQualification.objects.filter(
        worker=worker,
        position=shift.position,
        active=True,
    ).filter(Q(expires_on__isnull=True) | Q(expires_on__gte=day)).exists()
    if qualified:
        return None
    return _issue(
        policy.qualification_mode,
        'position_qualification',
        f'Keine aktive Qualifikation für Position „{shift.position.name}“ hinterlegt.',
        position=str(shift.position_id),
    )


def _schedule_issue(worker, shift, policy):
    if policy.schedule_membership_mode == SchedulingPolicy.Enforcement.OFF:
        return None
    groups = ScheduleGroup.objects.filter(active=True)
    if policy.schedule_id:
        groups = groups.filter(pk=policy.schedule_id)
    else:
        groups = groups.filter(locations=shift.location)
    group_ids = list(groups.values_list('id', flat=True))
    if not group_ids:
        return None
    member = ScheduleMembership.objects.filter(worker=worker, schedule_id__in=group_ids, active=True).exists()
    if member:
        return None
    return _issue(
        policy.schedule_membership_mode,
        'schedule_membership',
        'Mitarbeiter ist diesem Dienstplan nicht zugeordnet.',
        schedules=[str(item) for item in group_ids],
    )


def _tag_issues(worker, shift, policy):
    if policy.skill_tag_mode == SchedulingPolicy.Enforcement.OFF:
        return []
    requirements = PositionSkillTag.objects.filter(position=shift.position, required=True).select_related('tag')
    if not requirements.exists():
        return []
    day = _local_date(shift.starts_at)
    worker_tags = set(
        WorkerSkillTag.objects.filter(worker=worker, verified=True, tag__active=True)
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=day))
        .values_list('tag_id', flat=True)
    )
    issues = []
    for requirement in requirements:
        if requirement.tag_id not in worker_tags:
            issue = _issue(
                policy.skill_tag_mode,
                'required_tag',
                f'Erforderliche Qualifikation/Tag „{requirement.tag.name}“ fehlt.',
                tag=str(requirement.tag_id),
            )
            if issue:
                issues.append(issue)
    return issues


def _availability_issue(worker, shift, policy):
    if policy.availability_mode == SchedulingPolicy.Enforcement.OFF:
        return None
    unavailable = Availability.objects.filter(
        worker=worker,
        available=False,
        starts_at__lt=shift.ends_at,
        ends_at__gt=shift.starts_at,
    ).exists()
    if not unavailable:
        return None
    return _issue(policy.availability_mode, 'unavailable', 'Mitarbeiter ist in diesem Zeitraum nicht verfügbar.')


def _time_off_issue(worker, shift, policy):
    if policy.time_off_mode == SchedulingPolicy.Enforcement.OFF:
        return None
    start_day = _local_date(shift.starts_at)
    end_day = _local_date(shift.ends_at)
    blocked = TimeOffRequest.objects.filter(
        worker=worker,
        status=TimeOffRequest.Status.APPROVED,
        starts_on__lte=end_day,
        ends_on__gte=start_day,
    ).exists()
    if not blocked:
        return None
    return _issue(policy.time_off_mode, 'approved_time_off', 'Für diesen Zeitraum ist eine Abwesenheit genehmigt.')


def _overlap_issue(worker, shift):
    overlap = _assignment_queryset(worker, shift.starts_at, shift.ends_at, shift.id).exists()
    if not overlap:
        return None
    return {
        'code': 'overlap',
        'severity': 'block',
        'message': 'Mitarbeiter hat in diesem Zeitraum bereits eine Schicht.',
        'meta': {},
    }


def _rest_issues(worker, shift, policy):
    if policy.rest_mode == SchedulingPolicy.Enforcement.OFF or not policy.min_rest_hours:
        return []
    min_gap = timedelta(hours=float(policy.min_rest_hours))
    nearby = _assignment_queryset(
        worker,
        shift.starts_at - min_gap - timedelta(days=1),
        shift.ends_at + min_gap + timedelta(days=1),
        shift.id,
    ).order_by('starts_at')
    issues = []
    for assigned in nearby:
        gap = None
        if assigned.ends_at <= shift.starts_at:
            gap = shift.starts_at - assigned.ends_at
        elif assigned.starts_at >= shift.ends_at:
            gap = assigned.starts_at - shift.ends_at
        if gap is not None and gap < min_gap:
            issue = _issue(
                policy.rest_mode,
                'minimum_rest',
                f'Mindestruhezeit von {policy.min_rest_hours} Std. wird unterschritten.',
                other_shift=str(assigned.id),
                actual_hours=round(gap.total_seconds() / 3600, 2),
            )
            if issue:
                issues.append(issue)
    return issues


def _weekly_issues(worker, shift, policy):
    week_start, week_end = _week_bounds(shift.starts_at)
    week_shifts = list(_assignment_queryset(worker, week_start, week_end, shift.id))
    candidate_minutes = _worked_minutes(shift)
    existing_minutes = sum(_worked_minutes(item) for item in week_shifts)
    projected_minutes = existing_minutes + candidate_minutes
    issues = []

    if policy.hours_mode != SchedulingPolicy.Enforcement.OFF and policy.max_weekly_hours:
        maximum_minutes = int(Decimal(policy.max_weekly_hours) * 60)
        if projected_minutes > maximum_minutes:
            issue = _issue(
                policy.hours_mode,
                'max_weekly_hours',
                f'Geplante Wochenstunden überschreiten {policy.max_weekly_hours} Std.',
                projected_minutes=projected_minutes,
                maximum_minutes=maximum_minutes,
            )
            if issue:
                issues.append(issue)

    candidate_day = _local_date(shift.starts_at)
    days = {_local_date(item.starts_at) for item in week_shifts}
    days.add(candidate_day)
    if policy.days_mode != SchedulingPolicy.Enforcement.OFF and policy.max_days_per_week and len(days) > policy.max_days_per_week:
        issue = _issue(
            policy.days_mode,
            'max_days_per_week',
            f'Maximal {policy.max_days_per_week} Arbeitstage pro Woche werden überschritten.',
            projected_days=len(days),
        )
        if issue:
            issues.append(issue)

    if policy.days_mode != SchedulingPolicy.Enforcement.OFF and policy.max_consecutive_days:
        search_start = shift.starts_at - timedelta(days=int(policy.max_consecutive_days) + 7)
        search_end = shift.ends_at + timedelta(days=int(policy.max_consecutive_days) + 7)
        all_days = {_local_date(item.starts_at) for item in _assignment_queryset(worker, search_start, search_end, shift.id)}
        all_days.add(candidate_day)
        streak = 1
        cursor = candidate_day - timedelta(days=1)
        while cursor in all_days:
            streak += 1
            cursor -= timedelta(days=1)
        cursor = candidate_day + timedelta(days=1)
        while cursor in all_days:
            streak += 1
            cursor += timedelta(days=1)
        if streak > policy.max_consecutive_days:
            issue = _issue(
                policy.days_mode,
                'max_consecutive_days',
                f'Maximal {policy.max_consecutive_days} aufeinanderfolgende Arbeitstage werden überschritten.',
                projected_consecutive_days=streak,
            )
            if issue:
                issues.append(issue)

    return issues, projected_minutes


def evaluate_worker_for_shift(worker: WorkerProfile, shift: Shift):
    policy = policy_for_shift(shift)
    issues = []
    if not worker.active or not worker.user.is_active:
        issues.append({'code': 'inactive_worker', 'severity': 'block', 'message': 'Mitarbeiter ist nicht aktiv.', 'meta': {}})

    for single in (
        _overlap_issue(worker, shift),
        _availability_issue(worker, shift, policy),
        _time_off_issue(worker, shift, policy),
        _qualification_issue(worker, shift, policy),
        _schedule_issue(worker, shift, policy),
    ):
        if single:
            issues.append(single)
    issues.extend(_tag_issues(worker, shift, policy))
    issues.extend(_rest_issues(worker, shift, policy))
    weekly_issues, projected_minutes = _weekly_issues(worker, shift, policy)
    issues.extend(weekly_issues)

    blockers = [item for item in issues if item['severity'] == 'block']
    warnings = [item for item in issues if item['severity'] == 'warn']
    score = int(worker.ranking_points or 0) * 100 - int(projected_minutes / 60) - len(warnings) * 25
    return {
        'worker': str(worker.id),
        'worker_name': worker.user.get_full_name() or worker.user.email,
        'eligible': not blockers,
        'score': score,
        'projected_week_minutes': projected_minutes,
        'policy': {'id': str(policy.id) if policy.id else None, 'name': policy.name},
        'blockers': blockers,
        'warnings': warnings,
        'issues': issues,
    }


def ensure_worker_eligible(worker: WorkerProfile, shift: Shift):
    result = evaluate_worker_for_shift(worker, shift)
    if not result['eligible']:
        raise ValidationError(result['blockers'][0]['message'])
    return result


def eligible_workers_for_shift(shift: Shift, worker_ids=None):
    workers = WorkerProfile.objects.filter(active=True, user__is_active=True).select_related('user')
    if worker_ids:
        workers = workers.filter(pk__in=worker_ids)
    claimed_ids = set(
        ShiftSlot.objects.filter(shift=shift, status=ShiftSlot.Status.CLAIMED, worker__isnull=False).values_list('worker_id', flat=True)
    )
    results = [evaluate_worker_for_shift(worker, shift) for worker in workers.exclude(pk__in=claimed_ids)]
    results.sort(key=lambda row: (row['eligible'], row['score'], row['worker_name']), reverse=True)
    return results


@transaction.atomic
def assign_worker_to_shift(shift_id, worker: WorkerProfile, *, source='manager_assign'):
    shift = Shift.objects.select_for_update().select_related('position', 'location').get(pk=shift_id)
    ensure_worker_eligible(worker, shift)
    from .shift_service import ensure_slots, refresh_shift_state

    ensure_slots(shift)
    if ShiftSlot.objects.filter(shift=shift, worker=worker, status=ShiftSlot.Status.CLAIMED).exists():
        raise ValidationError('Mitarbeiter ist dieser Schicht bereits zugeordnet.')
    slot = ShiftSlot.objects.select_for_update().filter(
        shift=shift,
        status=ShiftSlot.Status.OPEN,
        worker__isnull=True,
    ).order_by('created_at').first()
    if not slot:
        raise ValidationError('Diese Schicht ist bereits vollständig besetzt.')
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = source
    slot.claimed_at = timezone.now()
    slot.released_at = None
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])
    refresh_shift_state(shift)
    return slot


@transaction.atomic
def auto_assign_shift(shift_id, worker_ids=None):
    shift = Shift.objects.select_for_update().select_related('position', 'location').get(pk=shift_id)
    from .shift_service import ensure_slots, refresh_shift_state

    ensure_slots(shift)
    open_slots = list(
        ShiftSlot.objects.select_for_update().filter(
            shift=shift,
            status=ShiftSlot.Status.OPEN,
            worker__isnull=True,
        ).order_by('created_at')
    )
    candidates = [row for row in eligible_workers_for_shift(shift, worker_ids=worker_ids) if row['eligible']]
    assigned = []
    for slot, candidate in zip(open_slots, candidates):
        worker = WorkerProfile.objects.select_related('user').get(pk=candidate['worker'])
        slot.worker = worker
        slot.status = ShiftSlot.Status.CLAIMED
        slot.source = 'auto_assign'
        slot.claimed_at = timezone.now()
        slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
        assigned.append({'slot': str(slot.id), **candidate})
    refresh_shift_state(shift)
    return {
        'shift': str(shift.id),
        'requested': int(shift.required_count or 1),
        'assigned': assigned,
        'assigned_count': len(assigned),
        'remaining_open': max(0, len(open_slots) - len(assigned)),
        'candidates': candidates,
    }


def apply_schedule_template(template: ScheduleTemplate, target_week_start, *, publish=False):
    monday = target_week_start - timedelta(days=target_week_start.weekday())
    created = []
    skipped = []
    for item in template.items.select_related('client', 'location', 'position').all():
        day = monday + timedelta(days=int(item.weekday))
        starts_at = timezone.make_aware(datetime.combine(day, item.start_time), timezone.get_current_timezone())
        end_day = day if item.end_time > item.start_time else day + timedelta(days=1)
        ends_at = timezone.make_aware(datetime.combine(end_day, item.end_time), timezone.get_current_timezone())
        existing = Shift.objects.filter(
            client=item.client,
            location=item.location,
            position=item.position,
            starts_at=starts_at,
            ends_at=ends_at,
        ).first()
        if existing:
            skipped.append(str(existing.id))
            continue
        shift = Shift.objects.create(
            client=item.client,
            location=item.location,
            position=item.position,
            starts_at=starts_at,
            ends_at=ends_at,
            break_minutes=item.break_minutes,
            required_count=item.required_count,
            notes=item.notes,
            status=Shift.Status.PUBLISHED if publish else Shift.Status.DRAFT,
            published_at=timezone.now() if publish else None,
            is_open=bool(publish),
        )
        created.append(str(shift.id))
    return {'created': created, 'skipped': skipped, 'week_start': monday.isoformat()}
