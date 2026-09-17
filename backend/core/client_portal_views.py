from pathlib import Path

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from . import views
from .client_order_planning import plan_client_order
from .client_portal_access import client_access_payload, get_client_portal_access
from .models import (
    ClientCompany,
    ClientOrder,
    Contract,
    Document,
    Location,
    Notification,
    PayrollStatement,
    Position,
    Shift,
    User,
    WorkerProfile,
    WorkerRating,
)
from .operational_notifications import notify_claimed_workers_shift_changed, notify_open_shift_available
from .permissions import IsAdminOrManager
from .portal_models import ClientShiftChangeRequest
from .shift_api import ShiftApiSerializer
from .shift_rules import automatic_break_minutes
from .shift_slots import ShiftSlot


DOCUMENT_MAX_BYTES = 20 * 1024 * 1024
DOCUMENT_EXTENSIONS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.txt', '.png', '.jpg', '.jpeg', '.webp', '.heic'}


def _account_name(user):
    return user.get_full_name() or user.username or user.email


def _parse_dt(value):
    if value in (None, ''):
        return None
    result = parse_datetime(str(value))
    if not result:
        return None
    if timezone.is_naive(result):
        result = timezone.make_aware(result, timezone.get_current_timezone())
    return result


def _shift_snapshot(shift):
    return {
        'shift_id': str(shift.id),
        'starts_at': shift.starts_at.isoformat() if shift.starts_at else None,
        'ends_at': shift.ends_at.isoformat() if shift.ends_at else None,
        'status': shift.status,
        'location_id': str(shift.location_id) if shift.location_id else None,
        'location_name': shift.location.name if shift.location_id else '',
        'notes': shift.notes or '',
        'required_count': int(shift.required_count or 1),
    }


def _request_payload(item):
    shift = item.shift
    return {
        'id': str(item.id),
        'shift_id': str(item.shift_id),
        'client_id': str(item.client_id),
        'client_name': item.client.name,
        'requested_by_id': str(item.requested_by_id),
        'requested_by_name': _account_name(item.requested_by),
        'requested_by_email': item.requested_by.email,
        'request_type': item.request_type,
        'status': item.status,
        'requested_starts_at': item.requested_starts_at,
        'requested_ends_at': item.requested_ends_at,
        'note': item.note,
        'created_at': item.created_at,
        'decided_at': item.decided_at,
        'decided_by_name': _account_name(item.decided_by) if item.decided_by_id else '',
        'admin_note': item.admin_note,
        'original_snapshot': item.original_snapshot,
        'decision_snapshot': item.decision_snapshot,
        'shift': {
            'starts_at': shift.starts_at,
            'ends_at': shift.ends_at,
            'status': shift.status,
            'location_name': shift.location.name if shift.location_id else '',
            'notes': shift.notes or '',
        },
    }


def _order_payload(order):
    return {
        'id': str(order.id),
        'client_id': str(order.client_id),
        'client_name': order.client.name,
        'title': order.title,
        'description': order.description,
        'location': str(order.location_id) if order.location_id else None,
        'location_name': order.location.name if order.location_id else '',
        'starts_at': order.starts_at,
        'ends_at': order.ends_at,
        'requested_staff': order.requested_staff,
        'functions': order.functions or [],
        'status': order.status,
        'created_at': order.created_at,
        'created_by_id': str(order.created_by_id) if order.created_by_id else None,
        'created_by_name': _account_name(order.created_by) if order.created_by_id else '',
        'created_by_email': order.created_by.email if order.created_by_id else '',
    }


def _document_payload(request, document):
    file_url = ''
    if document.file:
        file_url = request.build_absolute_uri(document.file.url)
    uploader = document.uploaded_by
    return {
        'id': str(document.id),
        'title': document.title,
        'folder': document.folder,
        'file': file_url,
        'created_at': document.created_at,
        'uploaded_by_name': _account_name(uploader) if uploader else 'A+ Solution',
        'uploaded_by_email': uploader.email if uploader else '',
    }


class ClientSafeRatingViewSet(views.RatingViewSet):
    """Keep ratings tenant-scoped and tied to a real completed client assignment."""

    def perform_create(self, serializer):
        if self.request.user.role != User.Role.CLIENT:
            return super().perform_create(serializer)

        _access, company = get_client_portal_access(self.request.user)
        worker = serializer.validated_data.get('worker')
        shift = serializer.validated_data.get('shift')
        if not shift:
            raise ValidationError({'shift': 'Bitte wähle den abgeschlossenen Einsatz aus.'})
        if not worker:
            raise ValidationError({'worker': 'Bitte wähle den eingesetzten Mitarbeiter aus.'})
        if shift.client_id != company.pk:
            raise ValidationError({'shift': 'Dieser Einsatz gehört nicht zu deinem Kundenkonto.'})
        if shift.status == Shift.Status.CANCELLED or shift.ends_at > timezone.now():
            raise ValidationError({'shift': 'Bewertungen sind erst nach einem tatsächlich durchgeführten Einsatz möglich.'})

        assigned = shift.worker_id == worker.pk or ShiftSlot.objects.filter(
            shift=shift,
            worker=worker,
            status=ShiftSlot.Status.CLAIMED,
        ).exists()
        if not assigned:
            raise ValidationError({'worker': 'Dieser Mitarbeiter war diesem Einsatz nicht zugeordnet.'})

        if WorkerRating.objects.filter(client=company, worker=worker, shift=shift).exists():
            raise ValidationError('Dieser Mitarbeitereinsatz wurde bereits bewertet.')

        obj = serializer.save(created_by=self.request.user, client=company)
        obj.worker.ranking_points += obj.score * 10
        obj.worker.save(update_fields=['ranking_points'])
        views.audit(self.request, 'rating.created', obj)


@api_view(['GET'])
def client_access(request):
    return Response(client_access_payload(request.user))


@api_view(['GET'])
def client_dashboard(request):
    if request.user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Übersicht ist nur im Kundenportal verfügbar.')
    access, company = get_client_portal_access(request.user)
    now = timezone.now()
    shifts = Shift.objects.filter(client=company, starts_at__gte=now).exclude(status=Shift.Status.CANCELLED)
    if access and access.read_only:
        if access.location_scope_id:
            shifts = shifts.filter(location_id=access.location_scope_id)
        else:
            shifts = shifts.none()
        return Response({
            'role': request.user.role,
            'active_orders': 0,
            'upcoming_shifts': shifts.count(),
            'contracts_to_sign': 0,
            'read_only': True,
        })
    return Response({
        'role': request.user.role,
        'active_orders': ClientOrder.objects.filter(
            client=company,
            status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING, ClientOrder.Status.CONFIRMED],
        ).count(),
        'upcoming_shifts': shifts.count(),
        'contracts_to_sign': Contract.objects.filter(
            client=company,
            client__contract_visibility_enabled=True,
            status__in=[Contract.Status.READY, Contract.Status.SENT],
        ).count(),
        'read_only': False,
    })


@api_view(['GET'])
def client_shifts(request):
    if request.user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Liste ist nur im Kundenportal verfügbar.')
    access, company = get_client_portal_access(request.user)
    qs = Shift.objects.filter(client=company).select_related('order', 'client', 'location', 'position').order_by('starts_at')
    if access and access.read_only:
        qs = qs.filter(location_id=access.location_scope_id) if access.location_scope_id else qs.none()
    serializer = ShiftApiSerializer(qs, many=True, context={'request': request})
    return Response(serializer.data)


@api_view(['GET'])
def client_order_metadata(request):
    if request.user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Funktion ist nur im Kundenportal verfügbar.')
    access, company = get_client_portal_access(request.user)
    if access and access.read_only:
        raise PermissionDenied('Dieser Zugang ist schreibgeschützt.')
    locations = Location.objects.filter(client=company, active=True).order_by('name')
    positions = Position.objects.filter(active=True).order_by('name')
    return Response({
        'client': {'id': str(company.id), 'name': company.name},
        'locations': [{'id': str(item.id), 'name': item.name, 'address': item.address} for item in locations],
        'positions': [{'id': str(item.id), 'name': item.name} for item in positions],
    })


@api_view(['GET', 'POST'])
def client_documents(request):
    if request.user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Funktion ist nur im Kundenportal verfügbar.')
    access, company = get_client_portal_access(request.user)
    if access and access.read_only:
        raise PermissionDenied('Dieser Zugang ist schreibgeschützt.')

    if request.method == 'GET':
        rows = Document.objects.filter(
            client=company,
            visibility__in=[Document.Visibility.CLIENT, Document.Visibility.SHARED],
        ).select_related('uploaded_by').order_by('-created_at')
        return Response([_document_payload(request, item) for item in rows])

    upload = request.FILES.get('file')
    if not upload:
        return Response({'detail': 'Bitte eine Datei oder ein Foto auswählen.'}, status=400)
    if upload.size > DOCUMENT_MAX_BYTES:
        return Response({'detail': 'Die Datei darf maximal 20 MB groß sein.'}, status=400)
    extension = Path(str(upload.name or '')).suffix.lower()
    if extension not in DOCUMENT_EXTENSIONS:
        return Response({'detail': 'Dieses Dateiformat wird nicht unterstützt.'}, status=400)
    folder = str(request.data.get('folder') or Document.Folder.GENERAL)
    if folder not in Document.Folder.values:
        folder = Document.Folder.GENERAL
    document = Document.objects.create(
        title=str(request.data.get('title') or upload.name).strip()[:250],
        file=upload,
        folder=folder,
        visibility=Document.Visibility.CLIENT,
        client=company,
        uploaded_by=request.user,
    )
    views.audit(request, 'client.document_uploaded', document, {'account': _account_name(request.user)})
    return Response(_document_payload(request, document), status=201)


@api_view(['GET'])
def client_rating_candidates(request):
    if request.user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Liste ist nur im Kundenportal verfügbar.')

    access, company = get_client_portal_access(request.user)
    if access and access.read_only:
        raise PermissionDenied('Dieser Zugang ist schreibgeschützt.')
    shifts = (
        Shift.objects.filter(client=company, ends_at__lte=timezone.now())
        .exclude(status=Shift.Status.CANCELLED)
        .select_related('client', 'location', 'position', 'worker__user')
        .prefetch_related('slots__worker__user')
        .order_by('-ends_at')[:150]
    )

    rows = []
    seen = set()
    for shift in shifts:
        workers = []
        if shift.worker_id:
            workers.append(shift.worker)
        workers.extend(
            slot.worker
            for slot in shift.slots.all()
            if slot.status == ShiftSlot.Status.CLAIMED and slot.worker_id
        )
        for worker in workers:
            key = (shift.pk, worker.pk)
            if key in seen:
                continue
            seen.add(key)
            if WorkerRating.objects.filter(client=shift.client, worker=worker, shift=shift).exists():
                continue
            rows.append({
                'shift_id': str(shift.id),
                'worker_id': str(worker.id),
                'worker_name': worker.user.get_full_name().strip() or worker.employee_number,
                'position_name': shift.position.name,
                'location_name': shift.location.name,
                'starts_at': shift.starts_at,
                'ends_at': shift.ends_at,
                'notes': shift.notes or '',
            })
    return Response(rows)


@api_view(['GET', 'POST'])
def client_shift_change_requests(request):
    if request.user.role != User.Role.CLIENT:
        raise PermissionDenied('Diese Funktion ist nur im Kundenportal verfügbar.')
    access, company = get_client_portal_access(request.user)
    if access and access.read_only:
        raise PermissionDenied('Dieser Zugang ist schreibgeschützt.')

    if request.method == 'GET':
        rows = ClientShiftChangeRequest.objects.filter(client=company).select_related(
            'client', 'shift__location', 'requested_by', 'decided_by'
        ).order_by('-created_at')[:100]
        return Response([_request_payload(item) for item in rows])

    shift = Shift.objects.select_related('client', 'location').filter(pk=request.data.get('shift'), client=company).first()
    if not shift:
        return Response({'detail': 'Die Schicht gehört nicht zu diesem Kundenkonto.'}, status=404)
    if shift.status == Shift.Status.CANCELLED:
        return Response({'detail': 'Diese Schicht ist bereits storniert.'}, status=400)
    if ClientShiftChangeRequest.objects.filter(shift=shift, status=ClientShiftChangeRequest.Status.PENDING).exists():
        return Response({'detail': 'Für diese Schicht gibt es bereits eine offene Anfrage.'}, status=400)

    request_type = str(request.data.get('request_type') or '').strip().lower()
    if request_type not in ClientShiftChangeRequest.RequestType.values:
        return Response({'detail': 'Bitte Änderung oder Stornierung auswählen.'}, status=400)
    requested_start = requested_end = None
    if request_type == ClientShiftChangeRequest.RequestType.CHANGE:
        requested_start = _parse_dt(request.data.get('starts_at'))
        requested_end = _parse_dt(request.data.get('ends_at'))
        if not requested_start or not requested_end or requested_end <= requested_start:
            return Response({'detail': 'Bitte gültigen neuen Beginn und neues Ende angeben.'}, status=400)

    item = ClientShiftChangeRequest.objects.create(
        shift=shift,
        client=company,
        requested_by=request.user,
        request_type=request_type,
        requested_starts_at=requested_start,
        requested_ends_at=requested_end,
        note=str(request.data.get('note') or '').strip(),
        original_snapshot=_shift_snapshot(shift),
    )
    label = 'Stornierung angefragt' if request_type == ClientShiftChangeRequest.RequestType.CANCEL else 'Schichtänderung angefragt'
    local_start = timezone.localtime(shift.starts_at).strftime('%d.%m.%y %H:%M')
    for recipient in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
        Notification.objects.create(
            user=recipient,
            kind=f'client-shift-request-{item.id}',
            title=label,
            body=f'{company.name} · {_account_name(request.user)} · {local_start} · {shift.location.name}',
            action_url='/operations',
        )
    views.audit(request, 'client.shift_change_requested', item, {
        'shift_id': str(shift.id),
        'requested_by': str(request.user.id),
        'request_type': request_type,
    })
    return Response(_request_payload(item), status=201)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def admin_client_requests(request):
    rows = ClientOrder.objects.filter(created_by__role=User.Role.CLIENT).select_related(
        'client', 'location', 'created_by'
    ).order_by('-created_at')
    pending = rows.filter(status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING])[:100]
    history = rows.exclude(status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING])[:50]
    positions = Position.objects.filter(active=True).order_by('name')
    locations = Location.objects.filter(active=True).select_related('client').order_by('client__name', 'name')
    return Response({
        'pending': [_order_payload(item) for item in pending],
        'history': [_order_payload(item) for item in history],
        'positions': [{'id': str(item.id), 'name': item.name} for item in positions],
        'locations': [
            {'id': str(item.id), 'name': item.name, 'client_id': str(item.client_id) if item.client_id else None, 'client_name': item.client.name if item.client_id else ''}
            for item in locations
        ],
    })


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def admin_client_request_decision(request, pk):
    order = ClientOrder.objects.select_related('client', 'location', 'created_by').filter(pk=pk, created_by__role=User.Role.CLIENT).first()
    if not order:
        return Response({'detail': 'Kundenanfrage wurde nicht gefunden.'}, status=404)
    decision = str(request.data.get('decision') or '').strip().lower()
    if decision not in {'approve', 'reject'}:
        return Response({'detail': 'decision muss approve oder reject sein.'}, status=400)
    if order.status not in {ClientOrder.Status.NEW, ClientOrder.Status.PLANNING}:
        return Response({'detail': 'Diese Kundenanfrage wurde bereits entschieden.'}, status=400)

    if 'title' in request.data:
        order.title = str(request.data.get('title') or '').strip()[:200]
    if 'description' in request.data:
        order.description = str(request.data.get('description') or '').strip()
    if 'requested_staff' in request.data:
        try:
            order.requested_staff = max(1, int(request.data.get('requested_staff') or 1))
        except (TypeError, ValueError):
            return Response({'detail': 'Anzahl Mitarbeiter ist ungültig.'}, status=400)
    if 'location' in request.data:
        location = Location.objects.filter(pk=request.data.get('location'), client=order.client, active=True).first()
        if not location:
            return Response({'detail': 'Der Einsatzort gehört nicht zu diesem Kunden.'}, status=400)
        order.location = location
    if 'starts_at' in request.data:
        order.starts_at = _parse_dt(request.data.get('starts_at'))
    if 'ends_at' in request.data:
        order.ends_at = _parse_dt(request.data.get('ends_at'))
    if not order.starts_at or not order.ends_at or order.ends_at <= order.starts_at:
        return Response({'detail': 'Beginn und Ende sind ungültig.'}, status=400)

    position = request.data.get('position')
    if position:
        chosen = Position.objects.filter(pk=position, active=True).first()
        if not chosen:
            return Response({'detail': 'Die ausgewählte Position wurde nicht gefunden.'}, status=400)
        order.functions = [str(chosen.id)]
    order.save(update_fields=['title', 'description', 'requested_staff', 'location', 'starts_at', 'ends_at', 'functions', 'updated_at'])

    if decision == 'reject':
        order.status = ClientOrder.Status.CANCELLED
        order.save(update_fields=['status', 'updated_at'])
        if order.created_by_id:
            Notification.objects.create(
                user=order.created_by,
                kind=f'client-order-decision-{order.id}-rejected',
                title='Personalanfrage abgelehnt',
                body=f'{order.title} · {_account_name(request.user)}',
                action_url='/orders',
            )
        views.audit(request, 'client.order_rejected', order, {'created_by': str(order.created_by_id)})
        return Response({'order': _order_payload(order), 'decision': 'rejected'})

    try:
        planned_order, shift, created = plan_client_order(order.pk, request, position)
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    if order.created_by_id:
        Notification.objects.create(
            user=order.created_by,
            kind=f'client-order-decision-{order.id}-approved',
            title='Personalanfrage bestätigt',
            body=f'{timezone.localtime(shift.starts_at):%d.%m.%y %H:%M} · {shift.location.name}',
            action_url='/schedule',
        )
    views.audit(request, 'client.order_approved', planned_order, {
        'shift_id': str(shift.id),
        'created_shift': created,
        'created_by': str(order.created_by_id),
    })
    return Response({
        'order': _order_payload(planned_order),
        'decision': 'approved',
        'created_shift': created,
        'shift': ShiftApiSerializer(shift, context={'request': request}).data,
    })


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def admin_shift_change_requests(request):
    rows = ClientShiftChangeRequest.objects.select_related(
        'client', 'shift__location', 'requested_by', 'decided_by'
    ).order_by('-created_at')
    return Response({
        'pending': [_request_payload(item) for item in rows.filter(status=ClientShiftChangeRequest.Status.PENDING)[:100]],
        'history': [_request_payload(item) for item in rows.exclude(status=ClientShiftChangeRequest.Status.PENDING)[:100]],
    })


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def admin_shift_change_request_decision(request, pk):
    with transaction.atomic():
        item = ClientShiftChangeRequest.objects.select_for_update().select_related(
            'client', 'shift__location', 'shift__position', 'requested_by'
        ).filter(pk=pk).first()
        if not item:
            return Response({'detail': 'Änderungsanfrage wurde nicht gefunden.'}, status=404)
        if item.status != ClientShiftChangeRequest.Status.PENDING:
            return Response({'detail': 'Diese Anfrage wurde bereits entschieden.'}, status=400)
        decision = str(request.data.get('decision') or '').strip().lower()
        if decision not in {'approve', 'reject'}:
            return Response({'detail': 'decision muss approve oder reject sein.'}, status=400)

        shift = item.shift
        now = timezone.now()
        if decision == 'approve':
            if item.request_type == ClientShiftChangeRequest.RequestType.CANCEL:
                shift.status = Shift.Status.CANCELLED
                shift.is_open = False
                shift.save(update_fields=['status', 'is_open', 'updated_at'])
            else:
                if not item.requested_starts_at or not item.requested_ends_at or item.requested_ends_at <= item.requested_starts_at:
                    return Response({'detail': 'Die angefragten Zeiten sind ungültig.'}, status=400)
                shift.starts_at = item.requested_starts_at
                shift.ends_at = item.requested_ends_at
                shift.break_minutes = automatic_break_minutes(shift.starts_at, shift.ends_at)
                shift.save(update_fields=['starts_at', 'ends_at', 'break_minutes', 'updated_at'])
            item.status = ClientShiftChangeRequest.Status.APPROVED
        else:
            item.status = ClientShiftChangeRequest.Status.REJECTED

        item.decided_by = request.user
        item.decided_at = now
        item.admin_note = str(request.data.get('note') or '').strip()
        item.decision_snapshot = _shift_snapshot(shift)
        item.save(update_fields=['status', 'decided_by', 'decided_at', 'admin_note', 'decision_snapshot', 'updated_at'])

    if decision == 'approve':
        if item.request_type == ClientShiftChangeRequest.RequestType.CANCEL:
            notify_claimed_workers_shift_changed(shift, title='Schicht storniert', reason='client-cancel-approved')
        else:
            notify_claimed_workers_shift_changed(shift, title='Schichtzeit aktualisiert', reason='client-change-approved')
            if shift.status == Shift.Status.PUBLISHED:
                notify_open_shift_available(shift, 'client-change-approved')
    Notification.objects.create(
        user=item.requested_by,
        kind=f'client-shift-request-decision-{item.id}-{decision}',
        title='Schichtanfrage genehmigt' if decision == 'approve' else 'Schichtanfrage abgelehnt',
        body=f'{timezone.localtime(shift.starts_at):%d.%m.%y %H:%M} · {shift.location.name}',
        action_url='/schedule',
    )
    views.audit(request, 'client.shift_change_decided', item, {
        'decision': decision,
        'requested_by_id': str(item.requested_by_id),
        'requested_by_name': _account_name(item.requested_by),
        'request_created_at': item.created_at.isoformat(),
        'shift_id': str(shift.id),
    })
    return Response(_request_payload(item))


@api_view(['GET'])
def folder_summary(request):
    user = request.user
    if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
        workers = [{
            'id': str(worker.id),
            'name': worker.user.get_full_name() or worker.user.email,
            'employee_number': worker.employee_number,
            'documents': Document.objects.filter(worker=worker).count(),
            'contracts': Contract.objects.filter(worker=worker).count(),
            'payroll': PayrollStatement.objects.filter(worker=worker).count(),
        } for worker in WorkerProfile.objects.filter(active=True).select_related('user')]
        clients = [{
            'id': str(client.id),
            'name': client.name,
            'customer_number': client.customer_number,
            'documents': Document.objects.filter(client=client).count(),
            'contracts': Contract.objects.filter(client=client).count(),
            'orders': ClientOrder.objects.filter(client=client).count(),
        } for client in ClientCompany.objects.filter(active=True)]
        return Response({'workers': workers, 'clients': clients})

    if user.role == User.Role.WORKER:
        worker = user.worker_profile
        return Response({'workers': [{
            'id': str(worker.id),
            'name': worker.user.get_full_name() or worker.user.email,
            'employee_number': worker.employee_number,
            'documents': Document.objects.filter(worker=worker).exclude(visibility=Document.Visibility.ADMIN).count(),
            'contracts': Contract.objects.filter(worker=worker).count(),
            'payroll': PayrollStatement.objects.filter(worker=worker).count(),
        }], 'clients': []})

    access, company = get_client_portal_access(user)
    if access and access.read_only:
        return Response({'workers': [], 'clients': []})
    return Response({'workers': [], 'clients': [{
        'id': str(company.id),
        'name': company.name,
        'customer_number': company.customer_number,
        'documents': Document.objects.filter(
            client=company,
            visibility__in=[Document.Visibility.CLIENT, Document.Visibility.SHARED],
        ).count(),
        'contracts': Contract.objects.filter(client=company).count() if company.contract_visibility_enabled else 0,
        'orders': ClientOrder.objects.filter(client=company).count(),
    }]})
