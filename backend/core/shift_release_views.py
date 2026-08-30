from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, Shift, User, WorkerProfile
from .permissions import IsAdminOrManager
from .premium_approval_models import ShiftReleaseRequest
from .services import audit
from .shift_service import ensure_worker_can_claim, release_shift
from .shift_slots import ShiftSlot


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


def _worker_name(worker):
    return worker.user.get_full_name() or worker.user.email or worker.employee_number


def _shift_details(shift):
    start = timezone.localtime(shift.starts_at)
    end = timezone.localtime(shift.ends_at)
    client = shift.client.name if shift.client_id else 'A+ Solution'
    location = shift.location.name if shift.location_id else 'Einsatzort'
    position = shift.position.name if shift.position_id else 'Einsatz'
    return f'{start:%d.%m.%Y} · {start:%H:%M}–{end:%H:%M} Uhr · {client} · {location} · {position}'


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def release_candidates(request, shift_id):
    """Return active colleagues who can still take this exact shift.

    The list is intentionally computed from the current planning rules instead of
    exposing every employee blindly. Eligibility is checked again when an admin
    approves the release because schedules can change between request and approval.
    """
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können Ersatzmitarbeiter auswählen.'}, status=403)

    worker = request.user.worker_profile
    shift = get_object_or_404(
        Shift.objects.select_related('client', 'location', 'position'),
        pk=shift_id,
    )
    if not shift.slots.filter(worker=worker, status=ShiftSlot.Status.CLAIMED).exists():
        return Response({'detail': 'Diese Schicht ist dir nicht aktiv zugewiesen.'}, status=400)

    candidates = []
    queryset = (
        WorkerProfile.objects.select_related('user')
        .filter(active=True, user__is_active=True)
        .exclude(pk=worker.pk)
        .exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
        .order_by('user__first_name', 'user__last_name', 'employee_number')
    )
    for candidate in queryset:
        try:
            ensure_worker_can_claim(candidate, shift)
        except Exception:
            continue
        candidates.append({
            'id': str(candidate.id),
            'name': _worker_name(candidate),
            'employee_number': candidate.employee_number,
        })

    return Response({
        'shift_id': str(shift.id),
        'candidates': candidates,
        'count': len(candidates),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_release(request, shift_id):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können eine Schichtfreigabe anfragen.'}, status=403)

    worker = request.user.worker_profile
    shift = get_object_or_404(
        Shift.objects.select_related('client', 'location', 'position'),
        pk=shift_id,
    )
    if shift.status in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
        return Response({'detail': 'Diese Schicht kann nicht mehr freigegeben werden.'}, status=400)
    if not shift.slots.filter(worker=worker, status=ShiftSlot.Status.CLAIMED).exists():
        return Response({'detail': 'Diese Schicht ist dir nicht aktiv zugewiesen.'}, status=400)

    requested_worker = None
    requested_worker_id = str(request.data.get('requested_worker') or '').strip()
    if requested_worker_id:
        requested_worker = (
            WorkerProfile.objects.select_related('user')
            .filter(pk=requested_worker_id, active=True, user__is_active=True)
            .exclude(pk=worker.pk)
            .exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
            .first()
        )
        if not requested_worker:
            return Response({'detail': 'Der gewünschte Ersatzmitarbeiter wurde nicht gefunden oder ist nicht aktiv.'}, status=400)
        try:
            ensure_worker_can_claim(requested_worker, shift)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            detail = detail[0] if isinstance(detail, list) else detail
            return Response({'detail': f'Der gewünschte Mitarbeiter kann diese Schicht aktuell nicht übernehmen: {detail}'}, status=400)

    row, created = ShiftReleaseRequest.objects.get_or_create(
        shift=shift,
        worker=worker,
        status=ShiftReleaseRequest.Status.PENDING,
        defaults={'requested_worker': requested_worker},
    )
    if not created and row.requested_worker_id != getattr(requested_worker, 'id', None):
        row.requested_worker = requested_worker
        row.save(update_fields=['requested_worker', 'updated_at'])

    if created:
        worker_name = request.user.get_full_name() or request.user.email
        requested_label = _worker_name(requested_worker) if requested_worker else 'kein Wunsch – als OpenShift freigeben'
        for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
            Notification.objects.create(
                user=recipient,
                kind=f'shift-release-request-{row.id}',
                title='Schichtfreigabe prüfen',
                body=f'{worker_name} · {_shift_details(shift)} · Wunsch: {requested_label}',
                action_url='/operations',
            )
        audit(request, 'shift.release_requested', shift, {
            'request_id': str(row.id),
            'worker': str(worker.id),
            'requested_worker': str(requested_worker.id) if requested_worker else None,
        })

    return Response({
        'id': str(row.id),
        'status': row.status,
        'pending_approval': True,
        'created': created,
        'requested_worker_id': str(row.requested_worker_id) if row.requested_worker_id else None,
        'requested_worker': _worker_name(row.requested_worker) if row.requested_worker_id else None,
    }, status=202)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def pending_release_requests(request):
    qs = ShiftReleaseRequest.objects.select_related(
        'worker__user', 'requested_worker__user',
        'shift__client', 'shift__location', 'shift__position',
    ).filter(status=ShiftReleaseRequest.Status.PENDING)
    return Response([{
        'id': str(row.id),
        'shift_id': str(row.shift_id),
        'worker_id': str(row.worker_id),
        'worker': _worker_name(row.worker),
        'requested_worker_id': str(row.requested_worker_id) if row.requested_worker_id else None,
        'requested_worker': _worker_name(row.requested_worker) if row.requested_worker_id else None,
        'starts_at': row.shift.starts_at.isoformat(),
        'ends_at': row.shift.ends_at.isoformat(),
        'client': row.shift.client.name if row.shift.client_id else 'A+ Solution',
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

    transferred_to = None
    with transaction.atomic():
        row = get_object_or_404(
            ShiftReleaseRequest.objects.select_for_update().select_related(
                'worker__user', 'requested_worker__user',
                'shift__client', 'shift__location', 'shift__position',
            ),
            pk=pk,
            status=ShiftReleaseRequest.Status.PENDING,
        )
        if decision == ShiftReleaseRequest.Status.APPROVED:
            try:
                release_shift(
                    row.shift_id,
                    row.worker,
                    admin_approved=True,
                    replacement_worker=row.requested_worker,
                )
                transferred_to = row.requested_worker
            except Exception as exc:
                detail = getattr(exc, 'detail', str(exc))
                detail = detail[0] if isinstance(detail, list) else detail
                return Response({'detail': str(detail)}, status=400)

        row.status = decision
        row.decided_by = request.user
        row.decision_note = str(request.data.get('note') or '').strip()
        row.save(update_fields=['status', 'decided_by', 'decision_note', 'updated_at'])

    if decision == ShiftReleaseRequest.Status.APPROVED:
        if transferred_to:
            replacement_name = _worker_name(transferred_to)
            worker_body = f'Deine Schicht wurde an {replacement_name} übertragen · {_shift_details(row.shift)}.'
            Notification.objects.create(
                user=transferred_to.user,
                kind=f'shift-release-transfer-{row.id}',
                title='Schicht bestätigen' if row.shift.confirmation_required else 'Neue Schicht zugeteilt',
                body=f'Dir wurde eine Schicht übertragen · {_shift_details(row.shift)}.',
                action_url='/schedule',
            )
        else:
            worker_body = f'Du wurdest aus der Schicht freigegeben · {_shift_details(row.shift)}.'
        title = 'Schichtfreigabe genehmigt'
    else:
        worker_body = f'Deine Schicht bleibt dir zugewiesen · {_shift_details(row.shift)}.'
        title = 'Schichtfreigabe abgelehnt'

    Notification.objects.create(
        user=row.worker.user,
        kind=f'shift-release-{row.id}-{decision}',
        title=title,
        body=worker_body,
        action_url='/schedule',
    )
    audit(request, f'shift.release_{decision}', row.shift, {
        'request_id': str(row.id),
        'worker': str(row.worker_id),
        'requested_worker': str(row.requested_worker_id) if row.requested_worker_id else None,
        'transferred': bool(decision == ShiftReleaseRequest.Status.APPROVED and transferred_to),
    })
    return Response({
        'id': str(row.id),
        'status': row.status,
        'transferred_to': str(transferred_to.id) if transferred_to else None,
    })
