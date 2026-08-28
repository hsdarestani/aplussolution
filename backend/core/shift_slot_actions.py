from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import Shift
from .permissions import IsAdminOrManager
from .services import audit
from .shift_api import ShiftApiSerializer
from .shift_service import ensure_slots, refresh_shift_state
from .shift_slots import ShiftSlot


def _shift_with_counts(pk):
    return Shift.objects.select_related('order', 'client', 'location', 'position').annotate(
        filled_count=Count(
            'slots',
            filter=Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False),
            distinct=True,
        ),
        open_count=Count(
            'slots',
            filter=Q(slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True),
            distinct=True,
        ),
    ).get(pk=pk)


def _editable_payload(data):
    allowed = {
        'client', 'location', 'position', 'starts_at', 'ends_at', 'notes',
        'confirmation_required', 'schedule_groups', 'status',
    }
    return {key: value for key, value in data.items() if key in allowed}


def _apply_payload(shift, data):
    serializer = ShiftApiSerializer(shift, data=_editable_payload(data), partial=True)
    serializer.is_valid(raise_exception=True)
    # Preserve Shift.worker while the model save signal runs. Passing worker=None
    # here used to make imported WIW one-person shifts look unassigned to the
    # ensure_shift_capacity signal, which immediately reopened the claimed slot.
    # refresh_shift_state below still derives the legacy Shift.worker mirror from
    # the authoritative ShiftSlot after the edit.
    shift = serializer.save()
    ensure_slots(shift)
    refresh_shift_state(shift)
    return shift


@api_view(['PATCH'])
@permission_classes([IsAdminOrManager])
def edit_shift_slot(request, shift_id, slot_id):
    """Edit one visual shift card, or all cards that share its parent demand.

    Capacity is represented by ShiftSlot. For a single-card edit we split the
    chosen slot into its own one-person Shift first. That preserves the learned
    WIW mental model: every card can be changed independently, while the
    explicit apply_all flag keeps the fast bulk-edit workflow.
    """
    apply_all = request.data.get('apply_all') in (True, 'true', '1', 1)

    with transaction.atomic():
        # Lock only the rows that are actually mutated. Joining nullable relations
        # (Shift.order and ShiftSlot.worker) before SELECT FOR UPDATE works on
        # SQLite but PostgreSQL correctly rejects it with:
        # "FOR UPDATE cannot be applied to the nullable side of an outer join".
        # That production-only database error was the generic mobile Sichern 500.
        shift = Shift.objects.select_for_update().filter(pk=shift_id).first()
        if not shift:
            return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)

        slot = ShiftSlot.objects.select_for_update().filter(
            pk=slot_id,
            shift=shift,
        ).exclude(status=ShiftSlot.Status.CANCELLED).first()
        if not slot:
            return Response({'detail': 'Schichtkarte wurde nicht gefunden.'}, status=404)

        # One-person shifts are already independent. Bulk/single therefore have
        # the same safe update path.
        if apply_all or int(shift.required_count or 1) <= 1:
            edited = _apply_payload(shift, request.data)
            audit(request, 'shift.card_bulk_updated' if apply_all else 'shift.card_updated', edited, {
                'slot': str(slot.id),
                'apply_all': apply_all,
            })
            result = ShiftApiSerializer(
                _shift_with_counts(edited.id), context={'request': request}
            ).data
            return Response({'shift': result, 'split': False, 'apply_all': apply_all})

        # Preserve the selected card before shrinking the parent capacity.
        selected = {
            'worker_id': slot.worker_id,
            'status': slot.status,
            'source': slot.source,
            'claimed_at': slot.claimed_at,
            'released_at': slot.released_at,
            'confirmation_status': slot.confirmation_status,
            'confirmation_requested_at': slot.confirmation_requested_at,
            'confirmation_decided_at': slot.confirmation_decided_at,
        }

        slot.status = ShiftSlot.Status.CANCELLED
        slot.save(update_fields=['status', 'updated_at'])
        shift.required_count = max(1, int(shift.required_count or 1) - 1)
        shift.save(update_fields=['required_count', 'updated_at'])
        ensure_slots(shift)
        refresh_shift_state(shift)

        clone = Shift.objects.create(
            order=shift.order,
            client=shift.client,
            location=shift.location,
            position=shift.position,
            worker=None,
            starts_at=shift.starts_at,
            ends_at=shift.ends_at,
            break_minutes=shift.break_minutes,
            status=shift.status,
            is_open=False,
            notes=shift.notes,
            required_count=1,
            confirmation_required=shift.confirmation_required,
            schedule_groups=shift.schedule_groups,
            published_at=shift.published_at,
            wiw_shift_id=None,
            wiw_payload={
                'source': 'split-card',
                'parent_shift_id': str(shift.id),
                'parent_slot_id': str(slot.id),
                'split_at': timezone.now().isoformat(),
            },
        )
        clone = _apply_payload(clone, request.data)

        clone_slot = ShiftSlot.objects.select_for_update().filter(
            shift=clone,
        ).exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at').first()
        if not clone_slot:
            ensure_slots(clone)
            clone_slot = ShiftSlot.objects.select_for_update().filter(
                shift=clone,
            ).exclude(status=ShiftSlot.Status.CANCELLED).order_by('created_at').first()

        clone_slot.worker_id = selected['worker_id']
        clone_slot.status = selected['status']
        clone_slot.source = 'split-card'
        clone_slot.claimed_at = selected['claimed_at']
        clone_slot.released_at = selected['released_at']
        clone_slot.confirmation_status = selected['confirmation_status']
        clone_slot.confirmation_requested_at = selected['confirmation_requested_at']
        clone_slot.confirmation_decided_at = selected['confirmation_decided_at']
        clone_slot.save(update_fields=[
            'worker', 'status', 'source', 'claimed_at', 'released_at',
            'confirmation_status', 'confirmation_requested_at',
            'confirmation_decided_at', 'updated_at',
        ])
        refresh_shift_state(clone)

        audit(request, 'shift.card_split_updated', clone, {
            'from_shift': str(shift.id),
            'from_slot': str(slot.id),
            'worker': str(selected['worker_id'] or ''),
        })

        return Response({
            'shift': ShiftApiSerializer(
                _shift_with_counts(clone.id), context={'request': request}
            ).data,
            'parent_shift': ShiftApiSerializer(
                _shift_with_counts(shift.id), context={'request': request}
            ).data,
            'split': True,
            'apply_all': False,
        })
