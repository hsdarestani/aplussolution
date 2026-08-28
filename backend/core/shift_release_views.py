from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, Shift, User
from .permissions import IsAdminOrManager
from .premium_approval_models import ShiftReleaseRequest
from .services import audit
from .shift_service import release_shift
from .shift_slots import ShiftSlot


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_release(request, shift_id):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können eine Schichtfreigabe anfragen.'}, status=403)

    worker = request.user.worker_profile
    shift = get_object_or_404(Shift.objects.select_related('location', 'position'), pk=shift_id)
    if shift.status in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        return Response({'detail': 'Diese Schicht kann nicht mehr freigegeben werden.'}, status=400)
    if not shift.slots.filter(worker=worker, status=ShiftSlot.Status.CLAIMED).exists():
        return Response({'detail': 'Diese Schicht ist dir nicht aktiv zugewiesen.'}, status=400)

    row, created = ShiftReleaseRequest.objects.get_or_create(
        shift=shift,
        worker=worker,
        status=ShiftReleaseRequest.Status.PENDING,
    )
    if created:
        worker_name = request.user.get_full_name() or request.user.email
        for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
            Notification.objects.create(
                user=recipient,
                kind=f'shift-release-request-{row.id}',
                title='Schichtfreigabe prüfen',
                body=f'{worker_name} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} · {shift.location.name}',
                action_url='/operations',
            )
        audit(request, 'shift.release_requested', shift, {'request_id': str(row.id), 'worker': str(worker.id)})

    return Response({
        'id': str(row.id),
        'status': row.status,
        'pending_approval': True,
        'created': created,
    }, status=202)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def pending_release_requests(request):
    qs = ShiftReleaseRequest.objects.select_related(
        'worker__user', 'shift__location', 'shift__position'
    ).filter(status=ShiftReleaseRequest.Status.PENDING)
    return Response([{
        'id': str(row.id),
        'shift_id': str(row.shift_id),
        'worker_id': str(row.worker_id),
        'worker': row.worker.user.get_full_name() or row.worker.user.email,
        'starts_at': row.shift.starts_at.isoformat(),
        'ends_at': row.shift.ends_at.isoformat(),
        'location': row.shift.location.name,
        'position': row.shift.position.name,
        'status': row.status,
        'created_at': row.created_at.isoformat(),
    } for row in qs[:500]])


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def decide_release_request(request, pk):
    decision = str(request.data.get('status') or '').strip().lower()
    if decision not in {ShiftReleaseRequest.Status.APPROVED, ShiftReleaseRequest.Status.REJECTED}:
        return Response({'detail': 'Status muss approved oder rejected sein.'}, status=400)

    with transaction.atomic():
        row = get_object_or_404(
            ShiftReleaseRequest.objects.select_for_update().select_related('worker__user', 'shift__location'),
            pk=pk,
            status=ShiftReleaseRequest.Status.PENDING,
        )
        if decision == ShiftReleaseRequest.Status.APPROVED:
            try:
                release_shift(row.shift_id, row.worker, admin_approved=True)
            except Exception as exc:
                detail = getattr(exc, 'detail', str(exc))
                detail = detail[0] if isinstance(detail, list) else detail
                return Response({'detail': str(detail)}, status=400)

        row.status = decision
        row.decided_by = request.user
        row.decision_note = str(request.data.get('note') or '').strip()
        row.save(update_fields=['status', 'decided_by', 'decision_note', 'updated_at'])

    Notification.objects.create(
        user=row.worker.user,
        kind=f'shift-release-{row.id}-{decision}',
        title='Schichtfreigabe genehmigt' if decision == ShiftReleaseRequest.Status.APPROVED else 'Schichtfreigabe abgelehnt',
        body=(
            f'Du wurdest aus der Schicht am {timezone.localtime(row.shift.starts_at):%d.%m.%Y %H:%M} freigegeben.'
            if decision == ShiftReleaseRequest.Status.APPROVED
            else f'Deine Schicht am {timezone.localtime(row.shift.starts_at):%d.%m.%Y %H:%M} bleibt dir zugewiesen.'
        ),
        action_url='/schedule',
    )
    audit(request, f'shift.release_{decision}', row.shift, {
        'request_id': str(row.id),
        'worker': str(row.worker_id),
    })
    return Response({'id': str(row.id), 'status': row.status})
