from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Notification, Shift
from .permissions import IsAdminOrManager
from .services import audit
from .shift_service import refresh_shift_state
from .shift_slots import ShiftSlot


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
    from django.utils.dateparse import parse_datetime

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
