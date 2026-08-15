from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Notification, Shift
from .permissions import IsAdminOrManager
from .services import audit
from .shift_service import refresh_shift_state
from .shift_slots import ShiftSlot


def _aware_day(day):
    return timezone.make_aware(datetime.combine(day, datetime.min.time()), timezone.get_current_timezone())


def _assign_copied_worker(clone, worker, source_slot, warnings):
    from .scheduling_rules import evaluate_worker_for_shift

    result = evaluate_worker_for_shift(worker, clone)
    if not result['eligible']:
        warnings.append({
            'source_slot': str(source_slot.id),
            'source_shift': str(source_slot.shift_id),
            'worker': str(worker.id),
            'worker_name': result['worker_name'],
            'target_shift': str(clone.id),
            'reasons': [item['message'] for item in result['blockers']],
        })
        return False
    target_slot = clone.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).order_by('created_at').first()
    if not target_slot:
        warnings.append({
            'source_slot': str(source_slot.id),
            'worker': str(worker.id),
            'target_shift': str(clone.id),
            'reasons': ['Kein freier Zielplatz vorhanden.'],
        })
        return False
    target_slot.worker = worker
    target_slot.status = ShiftSlot.Status.CLAIMED
    target_slot.source = 'schedule_copy'
    target_slot.claimed_at = timezone.now()
    target_slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'updated_at'])
    return True


def _copy_range_impl(request, source_start, source_end, target_start):
    delta = target_start - source_start
    source_qs = Shift.objects.filter(
        starts_at__gte=_aware_day(source_start),
        starts_at__lt=_aware_day(source_end),
    ).select_related('order', 'client', 'location', 'position').prefetch_related('slots__worker__user').order_by('starts_at')
    created = []
    skipped = []
    warnings = []
    copied_assignments = 0
    with transaction.atomic():
        for original in source_qs:
            starts_at = original.starts_at + delta
            ends_at = original.ends_at + delta
            duplicate = Shift.objects.filter(
                client=original.client,
                location=original.location,
                position=original.position,
                starts_at=starts_at,
                ends_at=ends_at,
            ).first()
            if duplicate:
                skipped.append({'source_shift': str(original.id), 'target_shift': str(duplicate.id), 'reason': 'Zielschicht existiert bereits.'})
                continue
            clone = Shift.objects.create(
                order=original.order,
                client=original.client,
                location=original.location,
                position=original.position,
                worker=None,
                starts_at=starts_at,
                ends_at=ends_at,
                break_minutes=original.break_minutes,
                status=Shift.Status.DRAFT,
                is_open=False,
                notes=original.notes,
                required_count=original.required_count,
            )
            created.append(str(clone.id))
            for source_slot in original.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user'):
                if _assign_copied_worker(clone, source_slot.worker, source_slot, warnings):
                    copied_assignments += 1
            refresh_shift_state(clone)
    audit(request, 'schedule.range_copied', request.user, {
        'source_start': source_start.isoformat(),
        'source_end': source_end.isoformat(),
        'target_start': target_start.isoformat(),
        'created': len(created),
        'copied_assignments': copied_assignments,
        'warnings': len(warnings),
    })
    return {
        'created': created,
        'skipped': skipped,
        'warnings': warnings,
        'copied_assignments': copied_assignments,
        'source_start': source_start,
        'source_end': source_end,
        'target_start': target_start,
    }


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def copy_range(request):
    source_start = parse_date(str(request.data.get('source_start') or ''))
    source_end = parse_date(str(request.data.get('source_end') or ''))
    target_start = parse_date(str(request.data.get('target_start') or ''))
    if not source_start or not source_end or not target_start or source_end <= source_start:
        return Response({'detail': 'Quellzeitraum und Zielbeginn sind erforderlich.'}, status=400)
    if (source_end - source_start).days > 31:
        return Response({'detail': 'Maximal 31 Tage können auf einmal kopiert werden.'}, status=400)
    return Response(_copy_range_impl(request, source_start, source_end, target_start), status=201)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def copy_week(request):
    source_start = parse_date(str(request.data.get('source_start') or ''))
    target_start = parse_date(str(request.data.get('target_start') or ''))
    if not source_start or not target_start:
        return Response({'detail': 'Quellwoche und Zielwoche sind erforderlich.'}, status=400)
    source_start -= timedelta(days=source_start.weekday())
    target_start -= timedelta(days=target_start.weekday())
    return Response(_copy_range_impl(request, source_start, source_start + timedelta(days=7), target_start), status=201)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def bulk_action(request):
    ids = [str(value) for value in (request.data.get('ids') or []) if value]
    action = str(request.data.get('action') or '').strip().lower()
    if not ids:
        return Response({'detail': 'Mindestens eine Schicht muss ausgewählt werden.'}, status=400)
    if action not in {'publish', 'unpublish', 'cancel', 'delete_drafts'}:
        return Response({'detail': 'Ungültige Bulk-Aktion.'}, status=400)

    qs = Shift.objects.filter(pk__in=ids).select_related('location').prefetch_related('slots__worker__user')
    changed = 0
    skipped = []
    with transaction.atomic():
        for shift in qs.select_for_update():
            claimed = shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).exists()
            if action == 'publish':
                if shift.status in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
                    skipped.append({'shift': str(shift.id), 'reason': 'Abgeschlossene/stornierte Schicht'})
                    continue
                shift.status = Shift.Status.PUBLISHED
                shift.published_at = timezone.now()
                shift.save(update_fields=['status', 'published_at', 'updated_at'])
                refresh_shift_state(shift)
                for slot in shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user'):
                    Notification.objects.get_or_create(
                        user=slot.worker.user,
                        kind=f'shift-published-{slot.id}',
                        defaults={
                            'title': 'Schicht veröffentlicht',
                            'body': f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name}',
                            'action_url': '/schedule',
                        },
                    )
                changed += 1
            elif action == 'unpublish':
                if claimed:
                    skipped.append({'shift': str(shift.id), 'reason': 'Bereits belegte Plätze vorhanden'})
                    continue
                shift.status = Shift.Status.DRAFT
                shift.is_open = False
                shift.save(update_fields=['status', 'is_open', 'updated_at'])
                changed += 1
            elif action == 'cancel':
                shift.status = Shift.Status.CANCELLED
                shift.is_open = False
                shift.save(update_fields=['status', 'is_open', 'updated_at'])
                changed += 1
                for slot in shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user'):
                    Notification.objects.create(
                        user=slot.worker.user,
                        kind=f'shift-cancelled-{slot.id}-{int(timezone.now().timestamp())}',
                        title='Schicht wurde storniert',
                        body=f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name}',
                        action_url='/schedule',
                    )
            else:
                if shift.status != Shift.Status.DRAFT or claimed:
                    skipped.append({'shift': str(shift.id), 'reason': 'Nur unbelegte Entwürfe können gelöscht werden'})
                    continue
                shift.delete()
                changed += 1

    audit(request, f'schedule.bulk_{action}', request.user, {'requested': len(ids), 'changed': changed, 'skipped': skipped})
    return Response({'action': action, 'requested': len(ids), 'changed': changed, 'skipped': skipped})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def clear_range(request):
    raw_start = request.data.get('starts_at')
    raw_end = request.data.get('ends_at')
    starts_at = parse_datetime(str(raw_start or ''))
    ends_at = parse_datetime(str(raw_end or ''))
    if not starts_at or not ends_at or ends_at <= starts_at:
        return Response({'detail': 'Gültiger Zeitraum ist erforderlich.'}, status=400)
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at)
    if timezone.is_naive(ends_at):
        ends_at = timezone.make_aware(ends_at)

    qs = Shift.objects.filter(starts_at__gte=starts_at, starts_at__lt=ends_at)
    if request.data.get('location'):
        qs = qs.filter(location_id=request.data['location'])
    drafts = qs.filter(status=Shift.Status.DRAFT).exclude(
        slots__status=ShiftSlot.Status.CLAIMED,
        slots__worker__isnull=False,
    ).distinct()
    count = drafts.count()
    ids = [str(value) for value in drafts.values_list('id', flat=True)]
    drafts.delete()
    audit(request, 'schedule.range_cleared', request.user, {'deleted': count, 'ids': ids[:100]})
    return Response({'deleted': count, 'ids': ids})
