from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Shift
from .permissions import IsAdminOrManager
from .services import audit
from .shift_service import refresh_shift_state
from .shift_slots import ShiftSlot


@api_view(['DELETE'])
@permission_classes([IsAdminOrManager])
def delete_shift_card(request, shift_id, slot_id):
    """Delete one visible staffing card without deleting sibling cards.

    A one-card shift is removed completely when it has no time entries. For a
    multi-person demand only the selected slot is removed and capacity is
    reduced by one. Historical shifts with recorded time remain immutable.
    """
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

        if active_count <= 1 or int(shift.required_count or 1) <= 1:
            audit(request, 'shift.card_deleted', shift, {'slot': str(slot.id), 'whole_shift': True})
            shift.delete()
            return Response({'deleted': True, 'whole_shift': True})

        slot.delete()
        shift.required_count = max(1, min(int(shift.required_count or 1) - 1, active_count - 1))
        shift.save(update_fields=['required_count', 'updated_at'])
        refresh_shift_state(shift)
        audit(request, 'shift.card_deleted', shift, {'slot': str(slot_id), 'whole_shift': False})
        return Response({
            'deleted': True,
            'whole_shift': False,
            'shift': str(shift.id),
            'required_count': shift.required_count,
        })
