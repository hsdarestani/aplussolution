from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Shift, WorkerProfile
from .operational_notifications import notify_open_shift_available
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


def ensure_shift_publish_allowed(shift: Shift) -> None:
    from .premium_services import get_policy

    policy = get_policy()
    if policy.allow_overlapping_open_shifts:
        return
    overlaps = Shift.objects.filter(
        location=shift.location,
        status=Shift.Status.PUBLISHED,
        starts_at__lt=shift.ends_at,
        ends_at__gt=shift.starts_at,
        slots__status=ShiftSlot.Status.OPEN,
    ).exclude(pk=shift.pk).distinct()
    if overlaps.exists():
        raise ValidationError('Überlappende OpenShifts sind in den Planungsregeln deaktiviert.')


def ensure_worker_can_claim(worker: WorkerProfile, shift: Shift) -> None:
    from .premium_services import violations

    # Reload DecimalField-backed values so cached/fresh ORM objects cannot
    # retain strings assigned before persistence.
    worker = WorkerProfile.objects.select_related('user').get(pk=worker.pk)

    # During the WIW/native cutover older single-person assignments may still
    # live on Shift.worker without a CLAIMED ShiftSlot. Keep those records in
    # conflict detection until the migration/audit path has fully normalized
    # historical data.
    legacy_overlap = Shift.objects.filter(
        worker=worker,
        starts_at__lt=shift.ends_at,
        ends_at__gt=shift.starts_at,
    ).exclude(pk=shift.pk).exclude(status=Shift.Status.CANCELLED).exists()
    if legacy_overlap:
        raise ValidationError('Du hast in diesem Zeitraum bereits eine Schicht.')

    issues = violations(worker, shift)
    if not issues:
        return
    messages = {
        'required_skills': 'Dir fehlt eine für diese Position erforderliche Qualifikation.',
        'unavailable': 'Du bist in diesem Zeitraum als nicht verfügbar eingetragen.',
        'approved_time_off': 'Für diesen Zeitraum liegt eine genehmigte Abwesenheit vor.',
        'overlap': 'Du hast in diesem Zeitraum bereits eine Schicht.',
        'multiple_shifts_per_day': 'Mehrere Schichten am selben Tag sind nicht erlaubt.',
        'minimum_rest': 'Der vorgeschriebene Ruheabstand zwischen Schichten wird unterschritten.',
        'max_hours_per_day': 'Die maximal erlaubten Tagesstunden würden überschritten.',
        'max_hours_per_week': 'Die maximal erlaubten Wochenstunden würden überschritten.',
        'max_days_per_week': 'Die maximal erlaubten Arbeitstage pro Woche würden überschritten.',
        'max_days_in_row': 'Die maximal erlaubten aufeinanderfolgenden Arbeitstage würden überschritten.',
        'monthly_hours': 'Das konfigurierte Monatsstundenlimit würde überschritten.',
    }
    raise ValidationError(messages.get(issues[0], f'Planungsregel verletzt: {issues[0]}'))


@transaction.atomic
def claim_shift(shift_id, worker: WorkerProfile, bypass_approval=False) -> ShiftSlot:
    shift = Shift.objects.select_for_update().select_related('location', 'position').get(pk=shift_id)
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
    slot.source = 'approved_pickup' if bypass_approval else 'worker_claim'
    now = timezone.now()
    slot.claimed_at = now
    slot.released_at = None
    # Claiming an OpenShift is itself an explicit acceptance.
    slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
    slot.confirmation_requested_at = now if shift.confirmation_required else None
    slot.confirmation_decided_at = now
    slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])
    refresh_shift_state(shift)
    return slot


@transaction.atomic
def release_shift(shift_id, worker: WorkerProfile, admin_approved=False) -> ShiftSlot:
    """Release a claimed slot only after an explicit admin/manager decision.

    Keeping this guard in the service layer closes the old direct API path too:
    a worker cannot bypass the release-request flow by calling /shifts/:id/release/.
    """
    if not admin_approved:
        raise ValidationError('Eine übernommene Schicht kann nur nach Freigabe durch die Administration abgegeben werden.')

    shift = Shift.objects.select_for_update().get(pk=shift_id)
    slot = ShiftSlot.objects.select_for_update().filter(
        shift=shift, worker=worker, status=ShiftSlot.Status.CLAIMED
    ).first()
    if not slot:
        raise ValidationError('Für dich wurde keine aktive Belegung dieser Schicht gefunden.')
    slot.worker = None
    slot.status = ShiftSlot.Status.OPEN
    slot.source = 'admin_approved_release'
    slot.released_at = timezone.now()
    slot.confirmation_status = ShiftSlot.ConfirmationStatus.CONFIRMED
    slot.confirmation_requested_at = None
    slot.confirmation_decided_at = None
    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'confirmation_status', 'confirmation_requested_at', 'confirmation_decided_at', 'updated_at'])
    if shift.status not in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        shift.status = Shift.Status.PUBLISHED
        shift.published_at = shift.published_at or timezone.now()
        shift.save(update_fields=['status', 'published_at', 'updated_at'])
    refresh_shift_state(shift)
    notify_open_shift_available(shift, 'release')
    return slot
