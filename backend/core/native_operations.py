from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from . import advanced_views as base
from . import slot_compat_views_v2 as slots
from .models import Notification, Shift
from .operational_notifications import notify_open_shift_available
from .services import audit
from .shift_service import (
    ensure_shift_publish_allowed,
    ensure_slots,
    ensure_worker_can_claim,
    refresh_shift_state,
)
from .shift_slots import ShiftSlot


# Canonical slot-aware implementations for the operational endpoints that were
# previously shadowed by premium_override_urls. Keeping the aliases here means
# both URL stacks resolve to the same behavior.
schedule_quality = slots.schedule_quality
swap_create = slots.swap_create
swap_decide = slots.swap_decide


def _assigned_workers(shift):
    """Return each assigned worker once, preferring native ShiftSlot ownership."""
    workers = []
    seen = set()
    claimed = (
        shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False)
        .select_related('worker__user')
        .order_by('created_at')
    )
    for slot in claimed:
        if slot.worker_id in seen:
            continue
        seen.add(slot.worker_id)
        workers.append(slot.worker)
    if shift.worker_id and shift.worker_id not in seen:
        workers.append(shift.worker)
    return workers


def _worker_name(worker):
    return worker.user.get_full_name() or worker.user.email


def _claim_slot(slot, worker, source):
    slot.worker = worker
    slot.status = ShiftSlot.Status.CLAIMED
    slot.source = source
    slot.claimed_at = timezone.now()
    slot.released_at = None
    slot.save(
        update_fields=[
            'worker',
            'status',
            'source',
            'claimed_at',
            'released_at',
            'updated_at',
        ]
    )


@api_view(['POST'])
def copy_week(request):
    denied = base._manager_required(request)
    if denied:
        return denied
    try:
        source_start = base._as_date(request.data.get('source_start'), 'Quellwoche')
        target_start = base._as_date(request.data.get('target_start'), 'Zielwoche')
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)

    source_start -= timedelta(days=source_start.weekday())
    target_start -= timedelta(days=target_start.weekday())
    if source_start == target_start:
        return Response({'detail': 'Quell- und Zielwoche müssen unterschiedlich sein.'}, status=400)

    source_end = source_start + timedelta(days=7)
    delta = target_start - source_start
    source_qs = (
        Shift.objects.filter(
            starts_at__gte=base._aware_start(source_start),
            starts_at__lt=base._aware_start(source_end),
        )
        .select_related('order', 'client', 'location', 'position', 'worker__user')
        .prefetch_related('slots__worker__user')
        .order_by('starts_at', 'created_at')
    )

    created = []
    warnings = []
    with transaction.atomic():
        for original in source_qs:
            clone = Shift.objects.create(
                order=original.order,
                client=original.client,
                location=original.location,
                position=original.position,
                worker=None,
                starts_at=original.starts_at + delta,
                ends_at=original.ends_at + delta,
                break_minutes=original.break_minutes,
                status=Shift.Status.DRAFT,
                is_open=False,
                notes=original.notes,
                required_count=original.required_count,
            )
            ensure_slots(clone)

            for worker in _assigned_workers(original):
                try:
                    ensure_worker_can_claim(worker, clone)
                except ValidationError as exc:
                    warnings.append(
                        {
                            'shift': str(original.id),
                            'worker': str(worker.id),
                            'message': (
                                f'{_worker_name(worker)}: {slots._validation_detail(exc)} '
                                'Die Position bleibt in der Kopie offen.'
                            ),
                        }
                    )
                    continue

                target_slot = (
                    ShiftSlot.objects.select_for_update()
                    .filter(
                        shift=clone,
                        status=ShiftSlot.Status.OPEN,
                        worker__isnull=True,
                    )
                    .order_by('created_at')
                    .first()
                )
                if target_slot is None:
                    warnings.append(
                        {
                            'shift': str(original.id),
                            'worker': str(worker.id),
                            'message': (
                                f'{_worker_name(worker)} konnte nicht übernommen werden, '
                                'weil keine freie Position in der Kopie vorhanden ist.'
                            ),
                        }
                    )
                    continue
                _claim_slot(target_slot, worker, 'copy_week')

            refresh_shift_state(clone)
            created.append(str(clone.id))

    audit(
        request,
        'schedule.week_copied',
        request.user,
        {'created': len(created), 'warnings': len(warnings), 'source': 'shift_slots'},
    )
    return Response({'created': created, 'warnings': warnings}, status=201)


@api_view(['POST'])
def bulk_publish(request):
    denied = base._manager_required(request)
    if denied:
        return denied
    ids = request.data.get('ids') or []
    if not ids:
        return Response({'published': 0})

    try:
        with transaction.atomic():
            shifts = list(
                Shift.objects.select_for_update()
                .filter(pk__in=ids)
                .select_related('worker__user', 'location', 'position')
                .prefetch_related('slots__worker__user')
                .order_by('starts_at')
            )
            published = 0
            for shift in shifts:
                was_published = shift.status == Shift.Status.PUBLISHED
                if shift.status in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
                    raise ValidationError('Stornierte oder abgeschlossene Schichten können nicht veröffentlicht werden.')
                ensure_slots(shift)
                ensure_shift_publish_allowed(shift)
                shift.status = Shift.Status.PUBLISHED
                shift.published_at = shift.published_at or timezone.now()
                shift.save(update_fields=['status', 'published_at', 'updated_at'])
                refresh_shift_state(shift)
                if not was_published:
                    notify_open_shift_available(shift, 'bulk-publish')

                for worker in _assigned_workers(shift):
                    Notification.objects.get_or_create(
                        user=worker.user,
                        kind=f'shift-published-{shift.id}',
                        defaults={
                            'title': 'Neue Schicht veröffentlicht',
                            'body': f'{shift.starts_at:%d.%m.%Y %H:%M}',
                            'action_url': '/schedule',
                        },
                    )
                published += 1
    except ValidationError as exc:
        return Response({'detail': slots._validation_detail(exc)}, status=400)

    audit(
        request,
        'schedule.bulk_published',
        request.user,
        {'count': published, 'source': 'shift_slots'},
    )
    return Response({'published': published})


@api_view(['GET'])
def export_schedule(request):
    denied = base._manager_required(request)
    if denied:
        return denied
    try:
        date_from = base._as_date(
            request.GET.get('date_from') or timezone.localdate().isoformat(),
            'Von',
        )
        date_to = base._as_date(
            request.GET.get('date_to') or (date_from + timedelta(days=30)).isoformat(),
            'Bis',
        )
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    if date_to < date_from:
        return Response({'detail': 'Bis muss am oder nach Von liegen.'}, status=400)

    shifts = (
        Shift.objects.filter(
            starts_at__gte=base._aware_start(date_from),
            starts_at__lt=base._aware_start(date_to + timedelta(days=1)),
        )
        .select_related('worker__user', 'client', 'location', 'position')
        .prefetch_related('slots__worker__user')
        .order_by('starts_at', 'created_at')
    )

    rows = []
    for shift in shifts:
        active_slots = list(
            shift.slots.exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at')
        )
        claimed_worker_ids = {
            slot.worker_id
            for slot in active_slots
            if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id
        }
        legacy_worker = (
            shift.worker
            if shift.worker_id and shift.worker_id not in claimed_worker_ids
            else None
        )

        if not active_slots:
            active_slots = [None]

        for slot in active_slots:
            worker = None
            if slot is not None and slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id:
                worker = slot.worker
            elif legacy_worker is not None and (
                slot is None
                or (slot.status == ShiftSlot.Status.OPEN and slot.worker_id is None)
            ):
                worker = legacy_worker
                legacy_worker = None

            rows.append(
                [
                    shift.starts_at.astimezone().strftime('%d.%m.%Y %H:%M'),
                    shift.ends_at.astimezone().strftime('%d.%m.%Y %H:%M'),
                    shift.client.name,
                    shift.location.name,
                    shift.position.name,
                    _worker_name(worker) if worker else 'OpenShift',
                    shift.get_status_display(),
                    shift.break_minutes,
                ]
            )

    return base._csv_response(
        f'dienstplan-{date_from:%Y%m%d}-{date_to:%Y%m%d}.csv',
        ['Beginn', 'Ende', 'Kunde', 'Einsatzort', 'Position', 'Mitarbeiter', 'Status', 'Pause (Min.)'],
        rows,
    )
