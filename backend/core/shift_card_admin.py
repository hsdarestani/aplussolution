from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Shift
from .permissions import IsAdminOrManager
from .operational_notifications import notify_worker_shift_event
from .services import audit
from .shift_service import refresh_shift_state
from .shift_slots import ShiftSlot


def _truthy(value, default=True):
    if value is None:
        return default
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off'}


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def remind_shift_card(request, shift_id, slot_id):
    shift = Shift.objects.filter(pk=shift_id).first()
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    slot = (
        ShiftSlot.objects.filter(pk=slot_id, shift=shift)
        .exclude(status=ShiftSlot.Status.CANCELLED)
        .select_related('worker__user')
        .first()
    )
    if not slot:
        return Response({'detail': 'Schichtkarte wurde nicht gefunden.'}, status=404)
    if not slot.worker_id:
        return Response({'detail': 'Diese OpenShift ist noch keinem Mitarbeiter zugewiesen.'}, status=400)

    user = slot.worker.user
    notify_worker_shift_event(user, shift, 'Erinnerung an deine Schicht', 'manual-reminder')
    audit(request, 'shift.card_reminder_sent', shift, {
        'slot': str(slot.id),
        'worker': str(slot.worker_id),
    })
    return Response({
        'sent': True,
        'worker': user.get_full_name() or user.email,
    })


@api_view(['DELETE'])
@permission_classes([IsAdminOrManager])
def delete_shift_card(request, shift_id, slot_id):
    """Delete one visible staffing card without deleting sibling cards.

    The caller explicitly decides whether an assigned employee should receive a
    push about the removal using ?notify_worker=1/0. Existing callers remain
    backward compatible and notify by default.
    """
    notify_worker = _truthy(request.query_params.get('notify_worker'), default=True)
    with transaction.atomic():
        shift = Shift.objects.select_for_update().filter(pk=shift_id).first()
        if not shift:
            return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
        if shift.time_entries.exists():
            return Response({'detail': 'Schichten mit Zeiterfassung können nicht gelöscht werden. Bitte Zeiten zuerst prüfen.'}, status=400)

        slot = ShiftSlot.objects.select_for_update().filter(
            pk=slot_id,
            shift=shift,
        ).exclude(status=ShiftSlot.Status.CANCELLED).first()
        if not slot:
            return Response({'detail': 'Schichtkarte wurde nicht gefunden.'}, status=404)

        active_count = ShiftSlot.objects.select_for_update().filter(
            shift=shift,
        ).exclude(status=ShiftSlot.Status.CANCELLED).count()

        worker_notified = False
        if slot.worker_id and notify_worker:
            slot = ShiftSlot.objects.select_related('worker__user').get(pk=slot.pk)
            notify_worker_shift_event(slot.worker.user, shift, 'Schicht aus deinem Dienstplan entfernt', 'card-delete')
            worker_notified = True

        if active_count <= 1 or int(shift.required_count or 1) <= 1:
            audit(request, 'shift.card_deleted', shift, {
                'slot': str(slot.id),
                'whole_shift': True,
                'worker_notified': worker_notified,
            })
            shift.delete()
            return Response({'deleted': True, 'whole_shift': True, 'worker_notified': worker_notified})

        slot.delete()
        shift.required_count = max(1, min(int(shift.required_count or 1) - 1, active_count - 1))
        shift.save(update_fields=['required_count', 'updated_at'])
        refresh_shift_state(shift)
        audit(request, 'shift.card_deleted', shift, {
            'slot': str(slot_id),
            'whole_shift': False,
            'worker_notified': worker_notified,
        })
        return Response({
            'deleted': True,
            'whole_shift': False,
            'shift': str(shift.id),
            'required_count': shift.required_count,
            'worker_notified': worker_notified,
        })
