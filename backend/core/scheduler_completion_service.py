from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Notification, Shift, TimeEntry
from .scheduler_completion_models import ScheduleAnnotation, SchedulerCompletionSettings, ShiftConfirmation
from .scheduling_models import ScheduleMembership
from .shift_slots import ShiftSlot
from .workplace_models import WorkplaceSettings


def _workplace_zone():
    name = WorkplaceSettings.load().timezone or 'Europe/Berlin'
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo('Europe/Berlin')


def _range_datetimes(starts_on, ends_on):
    zone = _workplace_zone()
    start = datetime.combine(starts_on, time.min, tzinfo=zone)
    end = datetime.combine(ends_on + timedelta(days=1), time.min, tzinfo=zone)
    return start, end


def annotation_shift_queryset(annotation):
    start, end = _range_datetimes(annotation.starts_on, annotation.ends_on)
    qs = Shift.objects.filter(starts_at__gte=start, starts_at__lt=end).exclude(status=Shift.Status.CANCELLED)
    if annotation.location_id:
        qs = qs.filter(location_id=annotation.location_id)
    if annotation.schedule_id:
        qs = qs.filter(location__in=annotation.schedule.locations.all())
    return qs.distinct()


def _worker_has_location_scope(worker, annotation):
    if not annotation.location_id:
        return True
    if ScheduleMembership.objects.filter(
        worker=worker, active=True, schedule__active=True, schedule__locations=annotation.location
    ).exists():
        return True
    start, end = _range_datetimes(annotation.starts_on, annotation.ends_on)
    return Shift.objects.filter(
        Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=worker),
        location=annotation.location,
        starts_at__lt=end,
        ends_at__gt=start,
    ).exclude(status=Shift.Status.CANCELLED).exists()


def annotation_applies_to_worker(annotation, worker):
    if annotation.schedule_id and not ScheduleMembership.objects.filter(
        worker=worker, schedule_id=annotation.schedule_id, active=True
    ).exists():
        return False
    return _worker_has_location_scope(worker, annotation)


def blocking_time_off_annotation(worker, starts_on, ends_on):
    qs = ScheduleAnnotation.objects.filter(
        active=True,
        kind=ScheduleAnnotation.Kind.BLOCK_TIME_OFF,
        starts_on__lte=ends_on,
        ends_on__gte=starts_on,
    ).select_related('schedule', 'location').prefetch_related('schedule__locations')
    for annotation in qs:
        if annotation_applies_to_worker(annotation, worker):
            return annotation
    return None


def ensure_time_off_allowed(worker, starts_on, ends_on):
    annotation = blocking_time_off_annotation(worker, starts_on, ends_on)
    if annotation:
        raise ValidationError(
            f'Für {annotation.starts_on:%d.%m.%Y}–{annotation.ends_on:%d.%m.%Y} sind Abwesenheitsanfragen gesperrt: {annotation.title}'
        )
    return True


def _notify_released_worker(slot, shift, title):
    if not slot.worker_id:
        return
    Notification.objects.create(
        user=slot.worker.user,
        kind=f'schedule-annotation-{shift.id}-{slot.worker_id}-{int(timezone.now().timestamp())}',
        title=title,
        body=f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name}',
        action_url='/schedule',
    )


@transaction.atomic
def apply_business_closed_action(annotation):
    if annotation.kind != ScheduleAnnotation.Kind.BUSINESS_CLOSED:
        return {'changed': 0, 'skipped': []}
    action = annotation.business_closed_action
    if action == ScheduleAnnotation.ClosedShiftAction.LEAVE:
        return {'changed': 0, 'skipped': []}
    changed = 0
    skipped = []
    now = timezone.now()
    for shift in annotation_shift_queryset(annotation).select_for_update().select_related('location').prefetch_related('slots__worker__user'):
        if shift.starts_at <= now:
            skipped.append({'shift': str(shift.id), 'reason': 'Bereits begonnene Schicht'})
            continue
        claimed = list(shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user'))
        if action == ScheduleAnnotation.ClosedShiftAction.UNPUBLISH:
            if claimed:
                skipped.append({'shift': str(shift.id), 'reason': 'Belegte Schicht'})
                continue
            shift.status = Shift.Status.DRAFT
            shift.is_open = False
            shift.save(update_fields=['status', 'is_open', 'updated_at'])
            changed += 1
        elif action == ScheduleAnnotation.ClosedShiftAction.OPEN:
            for slot in claimed:
                _notify_released_worker(slot, shift, 'Schicht wegen Betriebsschließung freigegeben')
                ShiftConfirmation.objects.filter(slot=slot).delete()
                slot.worker = None
                slot.status = ShiftSlot.Status.OPEN
                slot.source = 'business_closed_annotation'
                slot.released_at = now
                slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])
            if shift.status not in {Shift.Status.COMPLETED, Shift.Status.CANCELLED}:
                shift.status = Shift.Status.PUBLISHED
                shift.published_at = shift.published_at or now
                shift.is_open = True
                shift.save(update_fields=['status', 'published_at', 'is_open', 'updated_at'])
            changed += 1
        elif action == ScheduleAnnotation.ClosedShiftAction.DELETE:
            if TimeEntry.objects.filter(shift=shift).exists():
                skipped.append({'shift': str(shift.id), 'reason': 'Zeiterfassung vorhanden'})
                continue
            for slot in claimed:
                _notify_released_worker(slot, shift, 'Schicht wegen Betriebsschließung entfernt')
            shift.delete()
            changed += 1
    return {'changed': changed, 'skipped': skipped}


def sync_shift_confirmations(shift, *, force_reset=False):
    settings = SchedulerCompletionSettings.load()
    if not settings.require_shift_confirmation:
        ShiftConfirmation.objects.filter(shift=shift).delete()
        return []
    if shift.status not in {Shift.Status.PUBLISHED, Shift.Status.CONFIRMED}:
        return []
    publication_at = shift.published_at or timezone.now()
    active_slot_ids = []
    confirmations = []
    slots = shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user')
    for slot in slots:
        active_slot_ids.append(slot.id)
        confirmation, created = ShiftConfirmation.objects.get_or_create(
            slot=slot,
            defaults={
                'shift': shift,
                'worker': slot.worker,
                'publication_at': publication_at,
                'requested_at': timezone.now(),
            },
        )
        publication_changed = confirmation.publication_at != publication_at
        worker_changed = confirmation.worker_id != slot.worker_id
        if created or force_reset or publication_changed or worker_changed:
            confirmation.shift = shift
            confirmation.worker = slot.worker
            confirmation.publication_at = publication_at
            confirmation.requested_at = timezone.now()
            confirmation.confirmed_at = None
            confirmation.confirmed_by = None
            confirmation.save(update_fields=[
                'shift', 'worker', 'publication_at', 'requested_at', 'confirmed_at', 'confirmed_by', 'updated_at'
            ])
        confirmations.append(confirmation)
    ShiftConfirmation.objects.filter(shift=shift).exclude(slot_id__in=active_slot_ids).delete()
    return confirmations


def pending_confirmations_for_worker(worker):
    return ShiftConfirmation.objects.filter(
        worker=worker,
        confirmed_at__isnull=True,
        shift__starts_at__gte=timezone.now(),
        shift__status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
        slot__status=ShiftSlot.Status.CLAIMED,
        slot__worker=worker,
    ).select_related('shift__position', 'shift__location', 'slot').order_by('shift__starts_at')


@transaction.atomic
def confirm_shift_slot(worker, slot_id, user):
    slot = ShiftSlot.objects.select_for_update().select_related('shift', 'worker').filter(
        pk=slot_id, worker=worker, status=ShiftSlot.Status.CLAIMED
    ).first()
    if not slot:
        raise ValidationError('Diese Schichtbelegung gehört nicht zu deinem Profil.')
    sync_shift_confirmations(slot.shift)
    confirmation = ShiftConfirmation.objects.select_for_update().filter(slot=slot, worker=worker).first()
    if not confirmation:
        raise ValidationError('Für diese Schicht ist keine Bestätigung erforderlich.')
    if not confirmation.confirmed_at:
        confirmation.confirmed_at = timezone.now()
        confirmation.confirmed_by = user
        confirmation.save(update_fields=['confirmed_at', 'confirmed_by', 'updated_at'])
    return confirmation
