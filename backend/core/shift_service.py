from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Availability, Shift, WorkerProfile
from .shift_slots import ShiftSlot


def claimed_slots(shift: Shift):
    return shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False)


def open_slots(shift: Shift):
    return shift.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True)


def ensure_slots(shift: Shift) -> None:
    requested = max(1, int(shift.required_count or 1))
    claimed = claimed_slots(shift).count()
    if requested < claimed:
        raise ValidationError(f'Der Bedarf kann nicht unter {claimed} bereits belegte Plätze reduziert werden.')
    active = shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).count()
    if active < requested:
        ShiftSlot.objects.bulk_create([ShiftSlot(shift=shift) for _ in range(requested - active)])
    elif active > requested:
        removable = list(open_slots(shift).order_by('-created_at')[: active - requested])
        if len(removable) != active - requested:
            raise ValidationError('Belegte Plätze müssen zuerst freigegeben werden.')
        ShiftSlot.objects.filter(pk__in=[item.pk for item in removable]).update(status=ShiftSlot.Status.CANCELLED)
    refresh_shift_state(shift)


def refresh_shift_state(shift: Shift) -> Shift:
    claimed = list(claimed_slots(shift).select_related('worker')[:2])
    free = open_slots(shift).count()
    shift.worker = claimed[0].worker if int(shift.required_count or 1) == 1 and len(claimed) == 1 else None
    if shift.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED, Shift.Status.DRAFT}:
        shift.status = Shift.Status.CONFIRMED if free == 0 else Shift.Status.PUBLISHED
    shift.is_open = shift.status == Shift.Status.PUBLISHED and free > 0
    shift.save(update_fields=['worker', 'status', 'is_open', 'updated_at'])
    return shift


def ensure_worker_can_claim(worker: WorkerProfile, shift: Shift) -> None:
    if ShiftSlot.objects.filter(
        worker=worker,
        status=ShiftSlot.Status.CLAIMED,
        shift__starts_at__lt=shift.ends_at,
        shift__ends_at__gt=shift.starts_at,
    ).exclude(shift=shift).exists():
        raise ValidationError('Du hast in diesem Zeitraum bereits eine Schicht.')
    if Availability.objects.filter(
        worker=worker,
        available=False,
        starts_at__lt=shift.ends_at,
        ends_at__gt=shift.starts_at,
    ).exists():
        raise ValidationError('Du bist in diesem Zeitraum als nicht verfügbar eingetragen.')


@transaction.atomic
def claim_shift(shift_id, worker: WorkerProfile) -> ShiftSlot:
    shift = Shift.objects.select_for_update().select_related('location').get(pk=shift_id)
    if shift.status != Shift.Status.PUBLISHED:
        raise ValidationError('Diese Schicht ist nicht zur Übernahme veröffentlicht.')
    ensure_slots(shift)
    if ShiftSlot.objects.filter(shift=shift, worker=worker, status=ShiftSlot.Status.CLAIMED).exists():
        raise ValidationError('Du hast diese Schicht bereits übernommen.')
    ensure_worker_can_claim(worker, shift)
    slot = ShiftSlot.objects.select_for_update().filter(
        shift=shift, status=ShiftSlot.Status.OPEN, worker__isnull=True
    ).order_by('created_at').first()
    if not slot:
        raise ValidationError('Diese Schicht ist bereits vollständig besetzt.')
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = 'worker_claim'
    slot.claimed_at = timezone.now()
    slot.released_at = None
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])
    refresh_shift_state(shift)
    return slot


@transaction.atomic
def release_shift(shift_id, worker: WorkerProfile) -> ShiftSlot:
    shift = Shift.objects.select_for_update().get(pk=shift_id)
    slot = ShiftSlot.objects.select_for_update().filter(
        shift=shift, worker=worker, status=ShiftSlot.Status.CLAIMED
    ).first()
    if not slot:
        raise ValidationError('Für dich wurde keine aktive Belegung dieser Schicht gefunden.')
    slot.worker = None
    slot.status = ShiftSlot.Status.OPEN
    slot.source = 'worker_release'
    slot.released_at = timezone.now()
    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])
    if shift.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        shift.status = Shift.Status.PUBLISHED
        shift.published_at = shift.published_at or timezone.now()
        shift.save(update_fields=['status', 'published_at', 'updated_at'])
    refresh_shift_state(shift)
    return slot
