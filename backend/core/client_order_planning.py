from difflib import SequenceMatcher

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
    by_id = Position.objects.filter(pk=text, active=True).first()
    if by_id:
        return by_id
    return Position.objects.filter(name__iexact=text, active=True).first()


def _infer_position(order, explicit=None):
    position = _position_from_structured_value(explicit)
    if position:
        return position

    for value in order.functions or []:
        position = _position_from_structured_value(value)
        if position:
            return position

    haystack = _normalize(f'{order.title} {order.description}')
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


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def confirm_and_plan_order(request, pk):
    with transaction.atomic():
        order = (
            ClientOrder.objects.select_for_update()
            .select_related('client', 'location')
            .filter(pk=pk)
            .first()
        )
        if not order:
            return Response({'detail': 'Auftrag wurde nicht gefunden.'}, status=404)

        existing = order.shifts.exclude(status=Shift.Status.CANCELLED).order_by('starts_at').first()
        if existing:
            if order.status != ClientOrder.Status.CONFIRMED:
                order.status = ClientOrder.Status.CONFIRMED
                order.save(update_fields=['status', 'updated_at'])
            return Response({
                'detail': 'Der Auftrag ist bereits eingeplant.',
                'created': False,
                'shift': ShiftSerializer(existing).data,
            })

        if not order.location_id:
            return Response({'detail': 'Bitte zuerst einen Einsatzort im Auftrag hinterlegen.'}, status=400)
        if order.location.client_id not in (None, order.client_id):
            return Response({'detail': 'Der Einsatzort gehört nicht zu diesem Kunden.'}, status=400)
        if not order.starts_at or not order.ends_at or order.ends_at <= order.starts_at:
            return Response({'detail': 'Beginn und Ende des Auftrags sind ungültig.'}, status=400)

        position = _infer_position(order, request.data.get('position'))
        if not position:
            return Response({
                'detail': 'Die Funktion/Position konnte nicht eindeutig erkannt werden. Bitte im Kundenauftrag eine Position auswählen.'
            }, status=400)

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

    return Response({
        'detail': 'Auftrag wurde bestätigt und direkt eingeplant.',
        'created': True,
        'shift': ShiftSerializer(shift).data,
    }, status=201)
