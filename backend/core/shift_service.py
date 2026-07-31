from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Availability, Shift, ShiftAssignment, WorkerProfile


ACTIVE_ASSIGNMENT_STATUSES = [ShiftAssignment.Status.OPEN, ShiftAssignment.Status.CLAIMED]


def active_slots(shift: Shift):
    return shift.assignments.filter(status__in=ACTIVE_ASSIGNMENT_STATUSES)


def claimed_slots(shift: Shift):
    return shift.assignments.filter(status=ShiftAssignment.Status.CLAIMED, worker__isnull=False)


def open_slots(shift: Shift):
    return shift.assignments.filter(status=ShiftAssignment.Status.OPEN, worker__isnull=True)


def assigned_count(shift: Shift) -> int:
    return claimed_slots(shift).count()


def available_count(shift: Shift) -> int:
    return open_slots(shift).count()


def ensure_slots(shift: Shift) -> None:
    """Keep one persistent slot row for every requested worker place.

    Claimed places are never silently deleted when required_count is reduced. The
    caller receives a validation error instead and must release/cancel people first.
    """
    requested = max(1, int(shift.required_count or 1))
    claimed = claimed_slots(shift).count()
    if requested < claimed:
        raise ValidationError(
            f'Die benötigte Mitarbeiterzahl kann nicht unter {claimed} bereits besetzte Plätze reduziert werden.'
        )

    current = list(active_slots(shift).order_by('created_at'))
    missing = requested - len(current)
    if missing > 0:
        ShiftAssignment.objects.bulk_create([
            ShiftAssignment(shift=shift, status=ShiftAssignment.Status.OPEN, source=ShiftAssignment.Source.SYSTEM)
            for _ in range(missing)
        ])
    elif missing < 0:
        removable = list(open_slots(shift).order_by('-created_at')[: abs(missing)])
        if len(removable) != abs(missing):
            raise ValidationError('Besetzte Plätze müssen zuerst freigegeben werden.')
        ShiftAssignment.objects.filter(pk__in=[item.pk for item in removable]).update(
            status=ShiftAssignment.Status.CANCELLED,
            released_at=timezone.now(),
        )
    refresh_shift_state(shift)


def refresh_shift_state(shift: Shift, save=True) -> Shift:
    """Derive legacy fields and demand status from slots.

    The legacy ``worker`` field is retained temporarily for compatibility with old
    reports, but only represents a person when this is a single-place demand.
    """
    claimed = list(claimed_slots(shift).select_related('worker')[:2])
    available = available_count(shift)
    if int(shift.required_count or 1) == 1 and len(claimed) == 1:
        shift.worker = claimed[0].worker
    else:
        shift.worker = None

    if shift.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED, Shift.Status.DRAFT}:
        shift.status = Shift.Status.CONFIRMED if available == 0 else Shift.Status.PUBLISHED
    shift.is_open = shift.status == Shift.Status.PUBLISHED and available > 0
    if save:
        shift.save(update_fields=['worker', 'status', 'is_open', 'updated_at'])
    return shift


def ensure_worker_assignable(worker: WorkerProfile, shift: Shift) -> None:
    overlap = ShiftAssignment.objects.filter(
        worker=worker,
        status=ShiftAssignment.Status.CLAIMED,
        shift__starts_at__lt=shift.ends_at,
        shift__ends_at__gt=shift.starts_at,
    ).exclude(shift=shift).exists()
    # Transitional compatibility for data created before slot migration.
    legacy_overlap = Shift.objects.filter(
        worker=worker,
        starts_at__lt=shift.ends_at,
        ends_at__gt=shift.starts_at,
    ).exclude(pk=shift.pk).exclude(status=Shift.Status.CANCELLED).exists()
    if overlap or legacy_overlap:
        raise ValidationError('Du hast in diesem Zeitraum bereits eine Schicht.')

    if Availability.objects.filter(
        worker=worker,
        available=False,
        starts_at__lt=shift.ends_at,
        ends_at__gt=shift.starts_at,
    ).exists():
        raise ValidationError('Du bist in diesem Zeitraum als nicht verfügbar eingetragen.')


@transaction.atomic
def claim_shift(shift_id, worker: WorkerProfile) -> ShiftAssignment:
    shift = Shift.objects.select_for_update().select_related('client', 'location', 'position').get(pk=shift_id)
    if shift.status != Shift.Status.PUBLISHED:
        raise ValidationError('Diese Schicht ist nicht zur Übernahme veröffentlicht.')
    if ShiftAssignment.objects.filter(shift=shift, worker=worker, status=ShiftAssignment.Status.CLAIMED).exists():
        raise ValidationError('Du hast diese Schicht bereits übernommen.')
    ensure_worker_assignable(worker, shift)
    slot = (
        ShiftAssignment.objects.select_for_update()
        .filter(shift=shift, status=ShiftAssignment.Status.OPEN, worker__isnull=True)
        .order_by('created_at')
        .first()
    )
    if not slot:
        raise ValidationError('Diese Schicht ist bereits vollständig besetzt.')
    slot.worker = worker
    slot.status = ShiftAssignment.Status.CLAIMED
    slot.source = ShiftAssignment.Source.WORKER_CLAIM
    slot.claimed_at = timezone.now()
    slot.released_at = None
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])
    refresh_shift_state(shift)
    return slot


@transaction.atomic
def admin_assign(shift_id, worker: WorkerProfile, assignment_id=None) -> ShiftAssignment:
    shift = Shift.objects.select_for_update().get(pk=shift_id)
    ensure_worker_assignable(worker, shift)
    slots = ShiftAssignment.objects.select_for_update().filter(shift=shift)
    slot = slots.filter(pk=assignment_id).first() if assignment_id else None
    if slot and slot.status == ShiftAssignment.Status.CLAIMED and slot.worker_id != worker.id:
        raise ValidationError('Dieser Platz ist bereits belegt.')
    if slot is None:
        slot = slots.filter(status=ShiftAssignment.Status.OPEN, worker__isnull=True).order_by('created_at').first()
    if not slot:
        raise ValidationError('Keine freie Position mehr vorhanden.')
    slot.worker = worker
    slot.status = ShiftAssignment.Status.CLAIMED
    slot.source = ShiftAssignment.Source.ADMIN_OVERRIDE
    slot.claimed_at = timezone.now()
    slot.released_at = None
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])
    if shift.status == Shift.Status.DRAFT:
        shift.status = Shift.Status.PUBLISHED
        shift.published_at = shift.published_at or timezone.now()
        shift.save(update_fields=['status', 'published_at', 'updated_at'])
    refresh_shift_state(shift)
    return slot


@transaction.atomic
def release_shift(shift_id, worker: WorkerProfile) -> ShiftAssignment:
    shift = Shift.objects.select_for_update().get(pk=shift_id)
    slot = (
        ShiftAssignment.objects.select_for_update()
        .filter(shift=shift, worker=worker, status=ShiftAssignment.Status.CLAIMED)
        .first()
    )
    if not slot:
        raise ValidationError('Für dich wurde keine aktive Belegung dieser Schicht gefunden.')
    slot.worker = None
    slot.status = ShiftAssignment.Status.OPEN
    slot.source = ShiftAssignment.Source.WORKER_RELEASE
    slot.released_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])
    if shift.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        shift.status = Shift.Status.PUBLISHED
        shift.published_at = shift.published_at or timezone.now()
        shift.save(update_fields=['status', 'published_at', 'updated_at'])
    refresh_shift_state(shift)
    return slot
