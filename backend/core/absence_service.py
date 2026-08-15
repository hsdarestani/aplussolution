from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError

from .absence_models import CoverageOffer, ShiftAbsenceCase
from .models import Notification, Shift, TimeOffRequest, User, WorkerProfile
from .shift_service import ensure_slots, refresh_shift_state
from .shift_slots import ShiftSlot


ACTIVE_CASE_STATUSES = [
    ShiftAbsenceCase.Status.REPORTED,
    ShiftAbsenceCase.Status.COVERAGE_PENDING,
    ShiftAbsenceCase.Status.OFFERED,
    ShiftAbsenceCase.Status.MOVED_TO_OPEN,
]


class CoverageConflict(APIException):
    status_code = 409
    default_detail = 'Der Ersatzvorgang wurde zwischenzeitlich geändert.'
    default_code = 'coverage_conflict'


def _worker_name(worker):
    return worker.user.get_full_name() or worker.user.email


def _notify_managers(title, body, action_url='/operations'):
    for user in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
        Notification.objects.create(user=user, kind='absence-coverage', title=title, body=body, action_url=action_url)


def _claimed_slot_for_worker(shift, worker, requested_slot_id=None, *, lock=False):
    """Return the actual staffing slot, repairing pre-slot legacy single assignments when needed."""
    legacy_worker_id = shift.worker_id
    ensure_slots(shift)
    slots = ShiftSlot.objects.filter(shift=shift)
    if lock:
        slots = slots.select_for_update()
    if requested_slot_id:
        slot = slots.filter(pk=requested_slot_id).first()
        if not slot:
            raise ValidationError('Der ausgewählte Personalplatz wurde nicht gefunden.')
        if slot.worker_id == worker.id and slot.status == ShiftSlot.Status.CLAIMED:
            return slot
        if not (legacy_worker_id == worker.id and int(shift.required_count or 1) == 1 and slot.status == ShiftSlot.Status.OPEN):
            raise ValidationError('Dieser Personalplatz gehört nicht zum gemeldeten Mitarbeiter.')
    else:
        slot = slots.filter(worker=worker, status=ShiftSlot.Status.CLAIMED).first()
        if slot:
            return slot
        slot = slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).order_by('created_at').first()

    if legacy_worker_id == worker.id and int(shift.required_count or 1) == 1 and slot:
        slot.worker = worker
        slot.status = ShiftSlot.Status.CLAIMED
        slot.source = 'legacy_compat'
        slot.claimed_at = slot.claimed_at or timezone.now()
        slot.released_at = None
        slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])
        refresh_shift_state(shift)
        return slot
    raise ValidationError('Für diesen Mitarbeiter besteht keine aktive Belegung dieser Schicht.')


def _active_case_for_slot(slot):
    return ShiftAbsenceCase.objects.filter(slot=slot, status__in=ACTIVE_CASE_STATUSES).first()


@transaction.atomic
def report_absence(*, shift, absent_worker, reported_by, kind, note='', source=None, slot_id=None, time_off=None):
    shift = Shift.objects.select_for_update().select_related('location', 'position').get(pk=shift.pk)
    worker = WorkerProfile.objects.select_related('user').get(pk=absent_worker.pk)
    if shift.status in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        raise ValidationError('Für abgeschlossene oder stornierte Schichten kann kein Ausfall gemeldet werden.')
    if reported_by and reported_by.role == User.Role.WORKER and shift.ends_at < timezone.now():
        raise ValidationError('Eine bereits beendete Schicht kann nicht mehr als Ausfall gemeldet werden.')
    slot = _claimed_slot_for_worker(shift, worker, slot_id, lock=True)
    existing = _active_case_for_slot(slot)
    if existing:
        raise CoverageConflict('Für diesen Personalplatz besteht bereits ein offener Ausfall.')

    source = source or (ShiftAbsenceCase.Source.WORKER if reported_by and reported_by.role == User.Role.WORKER else ShiftAbsenceCase.Source.MANAGER)
    now = timezone.now()
    case = ShiftAbsenceCase.objects.create(
        shift=shift,
        slot=slot,
        absent_worker=worker,
        time_off_request=time_off,
        kind=kind if kind in ShiftAbsenceCase.Kind.values else ShiftAbsenceCase.Kind.OTHER,
        source=source,
        status=ShiftAbsenceCase.Status.COVERAGE_PENDING,
        reason_note=str(note or '').strip(),
        short_notice=shift.starts_at <= now + timedelta(hours=24),
        reported_by=reported_by,
        reported_at=now,
    )
    _notify_managers(
        'Mitarbeiterausfall gemeldet',
        f'{_worker_name(worker)} · {shift.position.name} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M}',
    )
    Notification.objects.create(
        user=worker.user,
        kind=f'absence-reported-{case.id}',
        title='Ausfall wurde erfasst',
        body=f'{shift.position.name} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M}',
        action_url='/operations',
    )
    return case


def coverage_candidates(case, worker_ids=None):
    from .scheduling_rules import eligible_workers_for_shift

    rows = eligible_workers_for_shift(case.shift, worker_ids=worker_ids)
    return [row for row in rows if row['worker'] != str(case.absent_worker_id)]


def _lock_case(case_id):
    return ShiftAbsenceCase.objects.select_for_update().select_related(
        'shift__location', 'shift__position', 'absent_worker__user', 'slot'
    ).get(pk=case_id)


def _ensure_case_open(case):
    if case.status not in ACTIVE_CASE_STATUSES:
        raise CoverageConflict('Dieser Ausfall ist bereits abgeschlossen.')


def _cancel_pending_offers(case, *, except_offer=None):
    qs = case.offers.filter(status=CoverageOffer.Status.PENDING)
    if except_offer:
        qs = qs.exclude(pk=except_offer.pk)
    qs.update(status=CoverageOffer.Status.CANCELLED, responded_at=timezone.now())


def _transfer_case_slot(case, replacement, *, source, actor=None, accepted_offer=None):
    from .scheduling_rules import ensure_worker_eligible

    ensure_worker_eligible(replacement, case.shift)
    slot = ShiftSlot.objects.select_for_update().filter(pk=case.slot_id, shift=case.shift).first()
    if not slot:
        raise CoverageConflict('Der ursprüngliche Personalplatz ist nicht mehr vorhanden.')
    if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id not in {None, case.absent_worker_id}:
        raise CoverageConflict('Der Personalplatz wurde bereits anderweitig besetzt.')
    slot.worker = replacement
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = source
    slot.claimed_at = timezone.now()
    slot.released_at = None
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])
    case.replacement_worker = replacement
    case.status = ShiftAbsenceCase.Status.COVERED
    case.resolved_by = actor
    case.resolved_at = timezone.now()
    case.save(update_fields=['replacement_worker', 'status', 'resolved_by', 'resolved_at', 'updated_at'])
    _cancel_pending_offers(case, except_offer=accepted_offer)
    refresh_shift_state(case.shift)
    Notification.objects.create(
        user=replacement.user,
        kind=f'coverage-assigned-{case.id}',
        title='Ersatzschicht übernommen',
        body=f'{case.shift.position.name} · {timezone.localtime(case.shift.starts_at):%d.%m.%Y %H:%M}',
        action_url='/schedule',
    )
    return case


@transaction.atomic
def move_case_to_open(case_id, actor):
    case = _lock_case(case_id)
    _ensure_case_open(case)
    slot = ShiftSlot.objects.select_for_update().filter(pk=case.slot_id, shift=case.shift).first()
    if not slot:
        raise CoverageConflict('Der Personalplatz wurde nicht gefunden.')
    if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id not in {None, case.absent_worker_id}:
        raise CoverageConflict('Der Personalplatz wurde bereits durch einen Ersatz besetzt.')
    slot.worker = None
    slot.status = ShiftSlot.Status.OPEN
    slot.source = 'absence_open_shift'
    slot.released_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])
    case.coverage_strategy = ShiftAbsenceCase.CoverageStrategy.OPEN_SHIFT
    case.status = ShiftAbsenceCase.Status.MOVED_TO_OPEN
    case.save(update_fields=['coverage_strategy', 'status', 'updated_at'])
    _cancel_pending_offers(case)
    if case.shift.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        case.shift.status = Shift.Status.PUBLISHED
        case.shift.published_at = case.shift.published_at or timezone.now()
        case.shift.save(update_fields=['status', 'published_at', 'updated_at'])
    refresh_shift_state(case.shift)
    return case


@transaction.atomic
def direct_replace(case_id, replacement, actor):
    case = _lock_case(case_id)
    _ensure_case_open(case)
    case.coverage_strategy = ShiftAbsenceCase.CoverageStrategy.DIRECT
    case.save(update_fields=['coverage_strategy', 'updated_at'])
    return _transfer_case_slot(case, replacement, source='absence_direct', actor=actor)


@transaction.atomic
def send_targeted_offers(case_id, actor, worker_ids=None, *, expires_in_hours=12, note=''):
    case = _lock_case(case_id)
    _ensure_case_open(case)
    rows = coverage_candidates(case, worker_ids=worker_ids)
    eligible = [row for row in rows if row['eligible']]
    if not eligible:
        raise ValidationError('Es wurde kein geeigneter Ersatzmitarbeiter gefunden.')
    now = timezone.now()
    requested_expiry = now + timedelta(hours=max(1, min(int(expires_in_hours or 12), 72)))
    shift_limit = case.shift.starts_at if case.shift.starts_at > now else case.shift.ends_at
    expiry = min(shift_limit, requested_expiry)
    if expiry <= now:
        raise ValidationError('Für diese bereits beendete Schicht können keine Ersatzanfragen mehr versendet werden.')
    offers = []
    for row in eligible:
        worker = WorkerProfile.objects.select_related('user').get(pk=row['worker'])
        offer, _ = CoverageOffer.objects.update_or_create(
            case=case,
            worker=worker,
            defaults={
                'status': CoverageOffer.Status.PENDING,
                'offered_by': actor,
                'offered_at': now,
                'expires_at': expiry,
                'responded_at': None,
                'eligibility_snapshot': row,
                'note': str(note or '')[:250],
            },
        )
        offers.append(offer)
        Notification.objects.create(
            user=worker.user,
            kind=f'coverage-offer-{offer.id}-{int(now.timestamp())}',
            title='Kurzfristige Schicht verfügbar',
            body=f'{case.shift.position.name} · {timezone.localtime(case.shift.starts_at):%d.%m.%Y %H:%M}',
            action_url='/operations',
        )
    case.coverage_strategy = ShiftAbsenceCase.CoverageStrategy.TARGETED
    case.status = ShiftAbsenceCase.Status.OFFERED
    case.save(update_fields=['coverage_strategy', 'status', 'updated_at'])
    return offers


@transaction.atomic
def respond_to_offer(offer_id, worker, decision):
    offer = CoverageOffer.objects.select_for_update().select_related('case__shift', 'case__slot').filter(pk=offer_id, worker=worker).first()
    if not offer:
        raise ValidationError('Ersatzanfrage wurde nicht gefunden.')
    if offer.status != CoverageOffer.Status.PENDING:
        raise CoverageConflict('Diese Ersatzanfrage wurde bereits beantwortet oder geschlossen.')
    now = timezone.now()
    if offer.expires_at and offer.expires_at <= now:
        offer.status = CoverageOffer.Status.EXPIRED
        offer.responded_at = now
        offer.save(update_fields=['status', 'responded_at', 'updated_at'])
        raise CoverageConflict('Diese Ersatzanfrage ist abgelaufen.')
    case = _lock_case(offer.case_id)
    _ensure_case_open(case)
    if decision == 'declined':
        offer.status = CoverageOffer.Status.DECLINED
        offer.responded_at = now
        offer.save(update_fields=['status', 'responded_at', 'updated_at'])
        if not case.offers.filter(status=CoverageOffer.Status.PENDING).exclude(pk=offer.pk).exists():
            case.status = ShiftAbsenceCase.Status.COVERAGE_PENDING
            case.save(update_fields=['status', 'updated_at'])
        return case, offer
    if decision != 'accepted':
        raise ValidationError('Antwort muss accepted oder declined sein.')
    offer.status = CoverageOffer.Status.ACCEPTED
    offer.responded_at = now
    offer.save(update_fields=['status', 'responded_at', 'updated_at'])
    case.coverage_strategy = ShiftAbsenceCase.CoverageStrategy.TARGETED
    case.save(update_fields=['coverage_strategy', 'updated_at'])
    case = _transfer_case_slot(case, worker, source='absence_targeted', actor=worker.user, accepted_offer=offer)
    return case, offer


@transaction.atomic
def resolve_uncovered(case_id, actor, note=''):
    case = _lock_case(case_id)
    _ensure_case_open(case)
    slot = ShiftSlot.objects.select_for_update().filter(pk=case.slot_id, shift=case.shift).first()
    if slot and slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id == case.absent_worker_id:
        slot.worker = None
        slot.status = ShiftSlot.Status.OPEN
        slot.source = 'absence_uncovered'
        slot.released_at = timezone.now()
        slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])
    elif slot and slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id not in {None, case.absent_worker_id}:
        raise CoverageConflict('Der Personalplatz wurde bereits durch einen Ersatz besetzt.')
    case.status = ShiftAbsenceCase.Status.RESOLVED_UNCOVERED
    case.manager_note = str(note or '').strip()
    case.resolved_by = actor
    case.resolved_at = timezone.now()
    case.save(update_fields=['status', 'manager_note', 'resolved_by', 'resolved_at', 'updated_at'])
    _cancel_pending_offers(case)
    if case.shift.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        case.shift.status = Shift.Status.PUBLISHED
        case.shift.published_at = case.shift.published_at or timezone.now()
        case.shift.save(update_fields=['status', 'published_at', 'updated_at'])
    refresh_shift_state(case.shift)
    return case


@transaction.atomic
def cancel_case(case_id, actor):
    case = _lock_case(case_id)
    _ensure_case_open(case)
    if actor.role == User.Role.WORKER and actor.id != case.absent_worker.user_id:
        raise ValidationError('Du kannst nur deinen eigenen Ausfall stornieren.')
    slot = ShiftSlot.objects.select_for_update().filter(pk=case.slot_id).first()
    if actor.role == User.Role.WORKER and slot and (slot.worker_id != case.absent_worker_id or case.replacement_worker_id):
        raise CoverageConflict('Der Ausfall kann nicht mehr storniert werden, weil die Schicht bereits neu disponiert wurde.')
    case.status = ShiftAbsenceCase.Status.CANCELLED
    case.resolved_by = actor
    case.resolved_at = timezone.now()
    case.save(update_fields=['status', 'resolved_by', 'resolved_at', 'updated_at'])
    _cancel_pending_offers(case)
    return case


def cases_for_approved_time_off(time_off, actor=None):
    if time_off.status != TimeOffRequest.Status.APPROVED:
        return []
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(time_off.starts_on, time.min), tz)
    end = timezone.make_aware(datetime.combine(time_off.ends_on + timedelta(days=1), time.min), tz)
    shifts = Shift.objects.filter(
        Q(slots__worker=time_off.worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=time_off.worker),
        starts_at__lt=end,
        ends_at__gt=start,
    ).exclude(status__in=[Shift.Status.CANCELLED, Shift.Status.COMPLETED]).distinct()
    created = []
    for shift in shifts:
        try:
            slot = _claimed_slot_for_worker(shift, time_off.worker)
        except ValidationError:
            continue
        existing = ShiftAbsenceCase.objects.filter(slot=slot, status__in=ACTIVE_CASE_STATUSES).first()
        if existing:
            created.append(existing)
            continue
        case = report_absence(
            shift=shift,
            absent_worker=time_off.worker,
            reported_by=actor,
            kind=ShiftAbsenceCase.Kind.APPROVED_TIME_OFF,
            note=time_off.reason,
            source=ShiftAbsenceCase.Source.TIME_OFF,
            slot_id=slot.id,
            time_off=time_off,
        )
        created.append(case)
    return created


def resolve_open_case_after_claim(slot, worker):
    """Called by OpenShift claiming so a coverage case closes automatically."""
    case = ShiftAbsenceCase.objects.filter(
        slot=slot,
        status=ShiftAbsenceCase.Status.MOVED_TO_OPEN,
        coverage_strategy=ShiftAbsenceCase.CoverageStrategy.OPEN_SHIFT,
    ).select_related('shift').first()
    if not case:
        return None
    case.replacement_worker = worker
    case.status = ShiftAbsenceCase.Status.COVERED
    case.resolved_by = worker.user
    case.resolved_at = timezone.now()
    case.save(update_fields=['replacement_worker', 'status', 'resolved_by', 'resolved_at', 'updated_at'])
    return case
