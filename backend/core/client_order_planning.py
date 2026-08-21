from difflib import SequenceMatcher
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ClientOrder, Position, Shift
from .permissions import IsAdminOrManager
from .serializers import ShiftSerializer
from .services import audit


def _normalize(value):
    return ' '.join(str(value or '').lower().replace('-', ' ').replace('_', ' ').split())


def _position_from_structured_value(value):
    if not value:
        return None
    if isinstance(value, dict):
        value = value.get('position_id') or value.get('id') or value.get('name') or value.get('role')
    text = str(value).strip()
    if not text:
        return None

    # Position IDs are UUIDs. Do not ask PostgreSQL to cast arbitrary client text
    # such as "Servicekräfte" to UUID; invalid casts can surface as a 500.
    try:
        position_id = UUID(text)
    except (TypeError, ValueError, AttributeError):
        position_id = None
    if position_id:
        by_id = Position.objects.filter(pk=position_id, active=True).first()
        if by_id:
            return by_id

    return Position.objects.filter(name__iexact=text, active=True).first()


def _function_values(raw):
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        return list(raw)
    if isinstance(raw, dict):
        return [raw]
    return [raw]


def _infer_position(order, explicit=None):
    position = _position_from_structured_value(explicit)
    if position:
        return position

    for value in _function_values(order.functions):
        position = _position_from_structured_value(value)
        if position:
            return position

    function_text = ' '.join(
        str(value.get('name') or value.get('role') or value.get('label') or '') if isinstance(value, dict) else str(value or '')
        for value in _function_values(order.functions)
    )
    haystack = _normalize(f'{order.title} {order.description} {function_text}')
    tokens = [token.strip('.,;:()[]{}') for token in haystack.split() if len(token) > 2]
    candidates = []
    for item in Position.objects.filter(active=True):
        name = _normalize(item.name)
        name_tokens = [part for part in name.split() if part not in {'qa', 'wiw', 'einsatz'}]
        if not name_tokens:
            name_tokens = name.split()

        score = 1.0 if name and name in haystack else 0.0
        for left in tokens:
            for right in name_tokens:
                score = max(score, SequenceMatcher(None, left, right).ratio())
        candidates.append((score, len(name), item))

    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1], row[2].name.lower()))
    best_score, _, best = candidates[0]
    return best if best_score >= 0.70 else None


def plan_client_order(order_id, request, explicit_position=None):
    """Confirm one client order and create its multi-slot OpenShift exactly once."""
    with transaction.atomic():
        order = (
            ClientOrder.objects.select_for_update()
            .select_related('client', 'location')
            .filter(pk=order_id)
            .first()
        )
        if not order:
            raise ValueError('Auftrag wurde nicht gefunden.')

        existing = order.shifts.exclude(status=Shift.Status.CANCELLED).order_by('starts_at').first()
        if existing:
            if order.status != ClientOrder.Status.CONFIRMED:
                order.status = ClientOrder.Status.CONFIRMED
                order.save(update_fields=['status', 'updated_at'])
            return order, existing, False

        if not order.location_id:
            raise ValueError('Bitte zuerst einen Einsatzort im Auftrag hinterlegen.')
        if order.location.client_id not in (None, order.client_id):
            raise ValueError('Der Einsatzort gehört nicht zu diesem Kunden.')
        if not order.starts_at or not order.ends_at or order.ends_at <= order.starts_at:
            raise ValueError('Beginn und Ende des Auftrags sind ungültig.')

        position = _infer_position(order, explicit_position)
        if not position:
            raise ValueError('Die Funktion/Position konnte nicht eindeutig erkannt werden.')

        shift = Shift.objects.create(
            order=order,
            client=order.client,
            location=order.location,
            position=position,
            starts_at=order.starts_at,
            ends_at=order.ends_at,
            break_minutes=0,
            status=Shift.Status.PUBLISHED,
            is_open=True,
            notes=order.description,
            required_count=max(1, int(order.requested_staff or 1)),
            published_at=timezone.now(),
        )
        order.status = ClientOrder.Status.CONFIRMED
        if not order.functions:
            order.functions = [str(position.id)]
        order.save(update_fields=['status', 'functions', 'updated_at'])
        audit(request, 'order.confirmed_and_planned', order, {
            'shift_id': str(shift.id),
            'position_id': str(position.id),
            'required_count': shift.required_count,
        })
        return order, shift, True


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def confirm_and_plan_order(request, pk):
    try:
        _order, shift, created = plan_client_order(pk, request, request.data.get('position'))
    except ValueError as exc:
        message = str(exc)
        return Response({'detail': message}, status=404 if message == 'Auftrag wurde nicht gefunden.' else 400)

    return Response({
        'detail': 'Auftrag wurde bestätigt und direkt eingeplant.' if created else 'Der Auftrag ist bereits eingeplant.',
        'created': created,
        'shift': ShiftSerializer(shift).data,
    }, status=201 if created else 200)
