from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import absence_views, admin_center_views, advanced_views, attendance_v4_views
from .absence_models import CoverageOffer, ShiftAbsenceCase
from .absence_service import report_absence
from .attendance_models import TimeEntryCorrection
from .attendance_v4_models import AttendanceNotice, AttendancePolicy, AttendanceTerminal
from .attendance_v4_service import scan_attendance_notices
from .models import (
    Availability,
    ClientCompany,
    ClientOrder,
    Contract,
    ContractTemplate,
    Document,
    Notification,
    PayrollStatement,
    Shift,
    ShiftSwapRequest,
    TimeEntry,
    TimeOffRequest,
    User,
    WorkerProfile,
)
from .permissions import IsAdminOrManager
from .serializers import AvailabilitySerializer, NotificationSerializer, ShiftSerializer
from .services import audit
from .shift_slots import ShiftSlot
from .workplace_access import (
    assignment_for,
    can_view_wage,
    capabilities_for_user,
    has_capability,
    location_in_scope,
    visible_locations,
    visible_workers,
    worker_in_scope,
)


MANAGER_ROLES = {User.Role.ADMIN, User.Role.MANAGER}


def _is_admin(user):
    return bool(user.role == User.Role.ADMIN or user.is_superuser)


def _is_manager(user):
    return user.role in MANAGER_ROLES or user.is_superuser


def _scope_is_all(user):
    if _is_admin(user):
        return True
    assignment = assignment_for(user)
    return bool(user.role == User.Role.MANAGER and (not assignment or assignment.scope_mode == 'all'))


def _require(user, capability):
    if not has_capability(user, capability):
        raise PermissionDenied('Keine Berechtigung für diese Funktion.')


def _visible_worker_ids(user):
    return list(visible_workers(user, WorkerProfile.objects.all()).values_list('id', flat=True))


def _visible_location_ids(user):
    return list(visible_locations(user).values_list('id', flat=True))


def _visible_client_ids(user):
    location_ids = _visible_location_ids(user)
    return list(LocationQuery.client_ids(location_ids))


class LocationQuery:
    @staticmethod
    def client_ids(location_ids):
        from .models import Location
        return Location.objects.filter(id__in=location_ids).values_list('client_id', flat=True).distinct()


class ScopedAttendancePolicyViewSet(attendance_v4_views.AttendancePolicyViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if _is_admin(user):
            return qs
        _require(user, 'attendance.view')
        return qs.filter(Q(location__isnull=True) | Q(location__in=visible_locations(user))).distinct()

    def _guard_location(self, serializer):
        if _is_admin(self.request.user):
            return
        location = serializer.validated_data.get('location', getattr(serializer.instance, 'location', None))
        if location is None:
            if not _scope_is_all(self.request.user):
                raise PermissionDenied('Globale Attendance-Regeln dürfen nur für den gesamten Betrieb verwaltet werden.')
            return
        if not location_in_scope(self.request.user, location):
            raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')

    def perform_create(self, serializer):
        _require(self.request.user, 'attendance.edit')
        self._guard_location(serializer)
        super().perform_create(serializer)

    def perform_update(self, serializer):
        _require(self.request.user, 'attendance.edit')
        self._guard_location(serializer)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        _require(self.request.user, 'attendance.edit')
        if not _is_admin(self.request.user):
            if instance.location_id is None and not _scope_is_all(self.request.user):
                raise PermissionDenied('Globale Attendance-Regeln dürfen nicht gelöscht werden.')
            if instance.location_id and not location_in_scope(self.request.user, instance.location):
                raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')
        instance.delete()


class ScopedAttendanceNoticeViewSet(attendance_v4_views.AttendanceNoticeViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if _is_admin(user):
            return qs
        _require(user, 'attendance.view')
        return qs.filter(worker_id__in=_visible_worker_ids(user)).distinct()

    def _set_state(self, request, obj, target):
        _require(request.user, 'attendance.edit')
        return super()._set_state(request, obj, target)


class ScopedAttendanceTerminalViewSet(attendance_v4_views.AttendanceTerminalViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if _is_admin(user):
            return qs
        _require(user, 'attendance.view')
        return qs.filter(location__in=visible_locations(user)).distinct()

    def _guard_location(self, serializer):
        if _is_admin(self.request.user):
            return
        location = serializer.validated_data.get('location', getattr(serializer.instance, 'location', None))
        if not location or not location_in_scope(self.request.user, location):
            raise PermissionDenied('Terminal-Standort liegt außerhalb deines Verantwortungsbereichs.')

    def create(self, request, *args, **kwargs):
        _require(request.user, 'attendance.edit')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._guard_location(serializer)
        token = AttendanceTerminal.issue_token()
        terminal = serializer.save(token_hash=AttendanceTerminal.hash_token(token), created_by=request.user)
        audit(request, 'attendance.terminal_created', terminal)
        data = self.get_serializer(terminal).data
        data['terminal_token'] = token
        data['terminal_token_note'] = 'Dieses Secret wird nur einmal angezeigt.'
        return Response(data, status=201)

    def perform_update(self, serializer):
        _require(self.request.user, 'attendance.edit')
        self._guard_location(serializer)
        terminal = serializer.save()
        audit(self.request, 'attendance.terminal_updated', terminal)

    def perform_destroy(self, instance):
        _require(self.request.user, 'attendance.edit')
        instance.delete()

    def rotate_token(self, request, pk=None):
        _require(request.user, 'attendance.edit')
        return super().rotate_token(request, pk=pk)


class ScopedAbsenceCaseViewSet(absence_views.AbsenceCaseViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if _is_admin(user):
            return qs
        if user.role == User.Role.MANAGER:
            _require(user, 'schedule.view')
            return qs.filter(shift__location__in=visible_locations(user)).distinct()
        return qs

    def get_permissions(self):
        if self.action in {'candidates', 'move_to_open', 'offer', 'replace', 'resolve_without_replacement', 'cancel'}:
            self.required_capability = 'schedule.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]


class ScopedCoverageOfferViewSet(absence_views.CoverageOfferViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if _is_admin(user):
            return qs
        if user.role == User.Role.MANAGER:
            _require(user, 'schedule.view')
            return qs.filter(case__shift__location__in=visible_locations(user)).distinct()
        return qs


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def attendance_exceptions(request):
    _require(request.user, 'attendance.view')
    now = timezone.now()
    worker_ids = _visible_worker_ids(request.user)
    locations = visible_locations(request.user)

    notices = AttendanceNotice.objects.select_related('worker__user', 'shift__position', 'shift__location').filter(
        worker_id__in=worker_ids,
        status__in=[AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED],
    ).order_by('severity', '-detected_at')[:200]
    unapproved = TimeEntry.objects.select_related('worker__user', 'shift__position').prefetch_related('attendance_breaks').filter(
        worker_id__in=worker_ids, clock_out__isnull=False, approved=False
    ).order_by('-clock_in')[:100]
    long_running = TimeEntry.objects.select_related('worker__user', 'shift__position').prefetch_related('attendance_breaks').filter(
        worker_id__in=worker_ids, clock_out__isnull=True, clock_in__lte=now - timedelta(hours=12)
    ).order_by('clock_in')[:100]
    corrections = TimeEntryCorrection.objects.select_related('entry', 'requested_by__user').filter(
        requested_by_id__in=worker_ids, status=TimeEntryCorrection.Status.PENDING
    ).order_by('created_at')[:100]
    notice_data = attendance_v4_views.AttendanceNoticeSerializer(notices, many=True).data
    return Response({
        'counts': {
            'attendance_notices': len(notice_data),
            'critical_notices': sum(item['severity'] == AttendanceNotice.Severity.CRITICAL for item in notice_data),
            'pending_corrections': len(corrections),
            'unapproved_entries': len(unapproved),
            'long_running_entries': len(long_running),
            'total': len(notice_data) + len(corrections) + len(unapproved) + len(long_running),
        },
        'notices': notice_data,
        'pending_corrections': [{
            'id': str(item.id), 'entry_id': str(item.entry_id), 'worker_id': str(item.requested_by_id),
            'worker_name': attendance_v4_views._worker_name(item.requested_by), 'original_clock_in': item.entry.clock_in,
            'original_clock_out': item.entry.clock_out, 'requested_clock_in': item.requested_clock_in,
            'requested_clock_out': item.requested_clock_out, 'reason': item.reason, 'status': item.status,
            'created_at': item.created_at,
        } for item in corrections],
        'unapproved_entries': [attendance_v4_views._entry_payload(entry, request) for entry in unapproved],
        'long_running_entries': [attendance_v4_views._entry_payload(entry, request) for entry in long_running],
        'policies': attendance_v4_views.AttendancePolicySerializer(
            AttendancePolicy.objects.select_related('location').filter(Q(location__isnull=True) | Q(location__in=locations)).distinct(), many=True
        ).data,
        'terminals': attendance_v4_views.AttendanceTerminalSerializer(
            AttendanceTerminal.objects.select_related('location').filter(location__in=locations).distinct(), many=True
        ).data,
    })


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def attendance_scan(request):
    _require(request.user, 'attendance.edit')
    if not _scope_is_all(request.user):
        return Response({'detail': 'Der globale Attendance-Scan ist nur mit betriebsweitem Zugriff verfügbar.'}, status=403)
    result = scan_attendance_notices()
    audit(request, 'attendance.notice_scan', request.user, result)
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def report_callout(request):
    shift = Shift.objects.select_related('position', 'location').filter(pk=request.data.get('shift')).first()
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    slot_id = request.data.get('slot')
    if request.user.role == User.Role.WORKER:
        worker = request.user.worker_profile
        owns_shift = Shift.objects.filter(pk=shift.pk).filter(
            Q(worker=worker) | Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED)
        ).exists()
        if not owns_shift:
            return Response({'detail': 'Du kannst nur einen eigenen Einsatz als Ausfall melden.'}, status=403)
        source = ShiftAbsenceCase.Source.WORKER
    elif _is_manager(request.user):
        _require(request.user, 'schedule.edit')
        if not _is_admin(request.user) and not location_in_scope(request.user, shift.location):
            return Response({'detail': 'Schicht liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
        worker = None
        if request.data.get('worker'):
            worker = WorkerProfile.objects.select_related('user').filter(pk=request.data.get('worker'), active=True).first()
        elif slot_id:
            slot = ShiftSlot.objects.select_related('worker__user').filter(pk=slot_id, shift=shift, worker__isnull=False).first()
            worker = slot.worker if slot else None
        elif shift.worker_id:
            worker = shift.worker
        if not worker:
            return Response({'detail': 'Mitarbeiter oder belegter Personalplatz ist erforderlich.'}, status=400)
        if not _is_admin(request.user) and not worker_in_scope(request.user, worker):
            return Response({'detail': 'Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
        source = ShiftAbsenceCase.Source.MANAGER
    else:
        return Response({'detail': 'Keine Berechtigung für Ausfallmeldungen.'}, status=403)
    try:
        case = report_absence(
            shift=shift,
            absent_worker=worker,
            reported_by=request.user,
            kind=str(request.data.get('kind') or ShiftAbsenceCase.Kind.OTHER),
            note=request.data.get('note', ''),
            source=source,
            slot_id=slot_id,
        )
    except Exception as exc:
        detail = getattr(exc, 'detail', str(exc))
        return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
    audit(request, 'absence.reported', case, {'short_notice': case.short_notice})
    return Response(absence_views.ShiftAbsenceCaseSerializer(case, context={'request': request}).data, status=status.HTTP_201_CREATED)


def _exception_scope_sets(user):
    worker_ids = {str(pk) for pk in _visible_worker_ids(user)}
    location_ids = _visible_location_ids(user)
    shift_ids = {str(pk) for pk in Shift.objects.filter(location_id__in=location_ids).values_list('id', flat=True)}
    client_ids = list(LocationQuery.client_ids(location_ids))
    contract_ids = {
        str(pk) for pk in Contract.objects.filter(
            Q(worker_id__in=worker_ids) | Q(client_id__in=client_ids)
        ).values_list('id', flat=True)
    }
    correction_ids = {str(pk) for pk in TimeEntryCorrection.objects.filter(requested_by_id__in=worker_ids).values_list('id', flat=True)}
    entry_ids = {str(pk) for pk in TimeEntry.objects.filter(worker_id__in=worker_ids).values_list('id', flat=True)}
    return worker_ids, shift_ids, contract_ids, correction_ids, entry_ids


def _filter_exception_items(user, items):
    if _is_admin(user):
        return items
    capabilities = set(capabilities_for_user(user))
    worker_ids, shift_ids, contract_ids, correction_ids, entry_ids = _exception_scope_sets(user)
    filtered = []
    for item in items:
        category = item.get('category')
        object_id = str(item.get('object_id') or '')
        meta = item.get('meta') or {}
        worker_id = str(meta.get('worker_id') or '')
        if category == 'staffing':
            allowed = 'schedule.view' in capabilities and object_id in shift_ids
        elif category == 'attendance':
            allowed = 'attendance.view' in capabilities and (
                worker_id in worker_ids or object_id in shift_ids or object_id in correction_ids or object_id in entry_ids
            )
        elif category == 'contracts':
            allowed = 'documents.manage' in capabilities and object_id in contract_ids
        elif category == 'documents':
            allowed = 'people.view' in capabilities and object_id in worker_ids
        elif category == 'integrations':
            allowed = 'workplace.manage' in capabilities and _scope_is_all(user)
        elif category == 'requests':
            allowed = worker_id in worker_ids and (
                'schedule.view' in capabilities or 'attendance.view' in capabilities
            )
        else:
            allowed = False
        if allowed:
            filtered.append(item)
    return filtered


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def admin_exception_center(request):
    items = _filter_exception_items(request.user, admin_center_views._exception_center_items(timezone.now()))
    category = str(request.GET.get('category') or '').strip()
    severity = str(request.GET.get('severity') or '').strip()
    query = str(request.GET.get('q') or '').strip().lower()
    if category and category != 'all':
        allowed = {part.strip() for part in category.split(',') if part.strip()}
        items = [item for item in items if item['category'] in allowed]
    if severity and severity != 'all':
        allowed = {part.strip() for part in severity.split(',') if part.strip()}
        items = [item for item in items if item['severity'] in allowed]
    if query:
        items = [item for item in items if query in f"{item['title']} {item['message']} {item['category']}".lower()]
    summary = {
        'total': len(items),
        'critical': sum(item['severity'] == 'critical' for item in items),
        'warning': sum(item['severity'] == 'warning' for item in items),
        'info': sum(item['severity'] == 'info' for item in items),
        'by_category': {
            name: sum(item['category'] == name for item in items)
            for name in ['staffing', 'attendance', 'contracts', 'documents', 'integrations', 'requests']
        },
    }
    try:
        limit = min(200, max(1, int(request.GET.get('limit') or 80)))
    except (TypeError, ValueError):
        limit = 80
    items.sort(key=admin_center_views._sort_value)
    return Response({'generated_at': timezone.now(), 'summary': summary, 'results': items[:limit], 'returned': min(len(items), limit)})


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def global_search(request):
    query = str(request.GET.get('q') or '').strip()
    if len(query) < 2:
        return Response({'query': query, 'results': [], 'groups': {}, 'total': 0})
    try:
        per_group = min(10, max(1, int(request.GET.get('limit') or 5)))
    except (TypeError, ValueError):
        per_group = 5
    capabilities = set(capabilities_for_user(request.user))
    worker_scope = visible_workers(request.user, WorkerProfile.objects.all())
    locations = visible_locations(request.user)
    client_ids = list(locations.values_list('client_id', flat=True).distinct())

    worker_q = Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(user__email__icontains=query) | Q(employee_number__icontains=query)
    workers = worker_scope.filter(worker_q).select_related('user').order_by('-active', 'user__last_name')[:per_group] if 'people.view' in capabilities else []
    worker_results = [
        admin_center_views._search_result('worker', worker, worker.user.get_full_name() or worker.user.email,
                                          f'{worker.employee_number} · {worker.user.email}', 'people',
                                          status='active' if worker.active else 'inactive', meta={'employee_number': worker.employee_number})
        for worker in workers
    ]

    client_q = Q(name__icontains=query) | Q(customer_number__icontains=query) | Q(address__icontains=query)
    clients = ClientCompany.objects.filter(id__in=client_ids).filter(client_q).order_by('-active', 'name')[:per_group] if 'clients.view' in capabilities else []
    client_results = [
        admin_center_views._search_result('client', client, client.name, client.customer_number, 'people', status='active' if client.active else 'inactive')
        for client in clients
    ]

    order_q = Q(title__icontains=query) | Q(description__icontains=query) | Q(client__name__icontains=query) | Q(location__name__icontains=query)
    orders = ClientOrder.objects.filter(location__in=locations).filter(order_q).select_related('client', 'location').order_by('-starts_at')[:per_group] if 'clients.view' in capabilities else []
    order_results = [
        admin_center_views._search_result('order', order, order.title, f'{order.client.name} · {order.starts_at:%d.%m.%Y %H:%M}',
                                          'orders', status=order.status, meta={'client': order.client.name, 'starts_at': order.starts_at})
        for order in orders
    ]

    shift_q = Q(client__name__icontains=query) | Q(location__name__icontains=query) | Q(location__address__icontains=query) | Q(position__name__icontains=query) | Q(order__title__icontains=query) | Q(notes__icontains=query)
    parsed_day = parse_date(query)
    if parsed_day:
        shift_q |= Q(starts_at__date=parsed_day)
    shifts = Shift.objects.filter(location__in=locations).filter(shift_q).select_related('client', 'location', 'position').annotate(
        open_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.OPEN), distinct=True),
        filled_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.CLAIMED), distinct=True),
    ).order_by('-starts_at')[:per_group] if 'schedule.view' in capabilities else []
    shift_results = [
        admin_center_views._search_result('shift', shift, f'{shift.position.name} · {shift.client.name}',
                                          f'{shift.location.name} · {shift.starts_at:%d.%m.%Y %H:%M}', 'schedule', status=shift.status,
                                          meta={'open_count': shift.open_count, 'filled_count': shift.filled_count, 'starts_at': shift.starts_at})
        for shift in shifts
    ]

    contract_q = Q(title__icontains=query) | Q(worker__user__first_name__icontains=query) | Q(worker__user__last_name__icontains=query) | Q(worker__user__email__icontains=query) | Q(client__name__icontains=query) | Q(template__name__icontains=query)
    contracts = Contract.objects.filter(Q(worker__in=worker_scope) | Q(client_id__in=client_ids)).filter(contract_q).select_related('worker__user', 'client', 'template').order_by('-created_at')[:per_group] if 'documents.manage' in capabilities else []
    contract_results = []
    for contract in contracts:
        subject = contract.worker.user.get_full_name() or contract.worker.user.email if contract.worker_id else contract.client.name if contract.client_id else contract.template.name
        contract_results.append(admin_center_views._search_result('contract', contract, contract.title, f'{subject} · {contract.template.name}', 'contracts', status=contract.status, meta={'ends_on': contract.ends_on}))

    groups = {'workers': worker_results, 'clients': client_results, 'orders': order_results, 'shifts': shift_results, 'contracts': contract_results}
    results = [item for group in groups.values() for item in group]
    return Response({'query': query, 'results': results, 'groups': groups, 'total': len(results)})


def _scoped_schedule_findings(user, date_from=None, date_to=None):
    now = timezone.now()
    start = date_from or now - timedelta(days=7)
    end = date_to or now + timedelta(days=90)
    locations = visible_locations(user)
    worker_scope = visible_workers(user, WorkerProfile.objects.all())
    shifts = list(Shift.objects.filter(location__in=locations, starts_at__lt=end, ends_at__gt=start).select_related(
        'worker__user', 'client', 'location', 'position', 'order'
    ).order_by('worker_id', 'starts_at'))
    conflicts = []
    by_worker = defaultdict(list)
    for shift in shifts:
        if shift.worker_id:
            by_worker[shift.worker_id].append(shift)
    for worker_shifts in by_worker.values():
        for previous, current in zip(worker_shifts, worker_shifts[1:]):
            if current.starts_at < previous.ends_at:
                conflicts.append({
                    'worker': str(current.worker_id), 'worker_name': current.worker.user.get_full_name() or current.worker.user.email,
                    'first_shift': str(previous.id), 'second_shift': str(current.id),
                    'first_window': [previous.starts_at, previous.ends_at], 'second_window': [current.starts_at, current.ends_at],
                    'severity': 'error', 'message': 'Zwei Schichten überschneiden sich.',
                })
    unavailable = []
    for availability in Availability.objects.filter(worker__in=worker_scope, available=False, starts_at__lt=end, ends_at__gt=start).select_related('worker__user'):
        for shift in by_worker.get(availability.worker_id, []):
            if shift.starts_at < availability.ends_at and shift.ends_at > availability.starts_at:
                unavailable.append({
                    'worker': str(availability.worker_id), 'worker_name': availability.worker.user.get_full_name() or availability.worker.user.email,
                    'shift': str(shift.id), 'starts_at': shift.starts_at, 'ends_at': shift.ends_at,
                    'message': 'Mitarbeiter ist in diesem Zeitraum als nicht verfügbar eingetragen.', 'severity': 'warning',
                })
    coverage = []
    for order in ClientOrder.objects.filter(location__in=locations, starts_at__lt=end, ends_at__gt=start,
                                             status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING, ClientOrder.Status.CONFIRMED]).select_related('client', 'location'):
        assigned = Shift.objects.filter(order=order).filter(Q(worker__isnull=False) | Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False)).distinct().count()
        open_count = Shift.objects.filter(order=order).filter(Q(is_open=True) | Q(slots__status=ShiftSlot.Status.OPEN)).distinct().count()
        gap = max(0, order.requested_staff - assigned)
        if gap:
            coverage.append({
                'order': str(order.id), 'client': str(order.client_id), 'title': order.title, 'client_name': order.client.name,
                'requested': order.requested_staff, 'assigned': assigned, 'open_shifts': open_count, 'gap': gap,
                'starts_at': order.starts_at, 'severity': 'warning', 'message': f'{gap} Position(en) sind noch nicht fest besetzt.',
            })
    month_start, month_end = advanced_views._month_bounds()
    month_start_dt, month_end_dt = advanced_views._aware_start(month_start), advanced_views._aware_start(month_end)
    overtime = []
    for worker in worker_scope.filter(active=True, monthly_hours__isnull=False).select_related('user'):
        minutes = sum(max(0, int((shift.ends_at - shift.starts_at).total_seconds() // 60) - shift.break_minutes)
                      for shift in Shift.objects.filter(worker=worker, location__in=locations, starts_at__lt=month_end_dt, ends_at__gte=month_start_dt).exclude(status=Shift.Status.CANCELLED))
        target = int(Decimal(worker.monthly_hours) * 60)
        if minutes > target:
            overtime.append({
                'worker': str(worker.id), 'worker_name': worker.user.get_full_name() or worker.user.email,
                'scheduled_minutes': minutes, 'target_minutes': target, 'difference_minutes': minutes - target,
                'severity': 'warning', 'message': 'Geplante Monatsstunden überschreiten das hinterlegte Stundenkonto.',
            })
    return {'conflicts': conflicts, 'unavailable_assignments': unavailable, 'coverage_gaps': coverage, 'overtime_risks': overtime}


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def operations_overview(request):
    user = request.user
    now = timezone.now()
    notifications = Notification.objects.filter(user=user).order_by('-created_at')[:30]
    data = {
        'role': user.role,
        'notifications': NotificationSerializer(notifications, many=True).data,
        'unread_notifications': Notification.objects.filter(user=user, read_at__isnull=True).count(),
        'readiness': None,
    }
    if _is_manager(user):
        _require(user, 'manager.access')
        caps = set(capabilities_for_user(user))
        locations = visible_locations(user)
        worker_scope = visible_workers(user, WorkerProfile.objects.all())
        client_ids = list(locations.values_list('client_id', flat=True).distinct())
        findings = _scoped_schedule_findings(user) if 'schedule.view' in caps else {
            'conflicts': [], 'unavailable_assignments': [], 'coverage_gaps': [], 'overtime_risks': []
        }
        swaps_qs = ShiftSwapRequest.objects.filter(shift__location__in=locations).select_related(
            'shift__position', 'requested_by__user', 'offered_to__user'
        ).order_by('-created_at')
        current_month_start, current_month_end = advanced_views._month_bounds()
        month_start_dt, month_end_dt = advanced_views._aware_start(current_month_start), advanced_views._aware_start(current_month_end)
        estimated_cost = None
        if 'payroll.view' in caps and can_view_wage(user):
            cost = Decimal('0')
            for shift in Shift.objects.filter(location__in=locations, worker__in=worker_scope, starts_at__lt=month_end_dt, ends_at__gte=month_start_dt).exclude(status=Shift.Status.CANCELLED).select_related('worker'):
                minutes = max(0, int((shift.ends_at - shift.starts_at).total_seconds() // 60) - shift.break_minutes)
                rate = shift.worker.tariff_hourly_rate or Decimal('0')
                allowance = shift.worker.extra_allowance or Decimal('0')
                cost += (Decimal(minutes) / Decimal(60)) * (rate + allowance)
            estimated_cost = str(cost.quantize(Decimal('0.01')))
        contract_scope = Contract.objects.filter(Q(worker__in=worker_scope) | Q(client_id__in=client_ids))
        data.update({
            **findings,
            'readiness': advanced_views._readiness() if 'workplace.manage' in caps else None,
            'estimated_monthly_labor_cost': estimated_cost,
            'pending_swaps': swaps_qs.filter(status=ShiftSwapRequest.Status.PENDING).count() if 'schedule.view' in caps else 0,
            'swaps': [advanced_views._serialize_swap(item) for item in swaps_qs[:50]] if 'schedule.view' in caps else [],
            'swap_candidates': [
                {'id': str(worker.id), 'name': worker.user.get_full_name() or worker.user.email}
                for worker in worker_scope.filter(active=True).select_related('user').order_by('user__first_name')
            ] if 'schedule.view' in caps else [],
            'pending_time_off': TimeOffRequest.objects.filter(worker__in=worker_scope, status=TimeOffRequest.Status.PENDING).count() if 'attendance.view' in caps else 0,
            'unapproved_time_entries': TimeEntry.objects.filter(worker__in=worker_scope, approved=False, clock_out__isnull=False).count() if 'attendance.view' in caps else 0,
            'missing_clock_outs': TimeEntry.objects.filter(worker__in=worker_scope, clock_out__isnull=True, clock_in__lt=now - timedelta(hours=16)).count() if 'attendance.view' in caps else 0,
            'contracts_due_30': contract_scope.filter(ends_on__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30)), status__in=[Contract.Status.READY, Contract.Status.SENT, Contract.Status.SIGNED]).count() if 'documents.manage' in caps else 0,
            'active_workers': worker_scope.filter(active=True).count() if 'people.view' in caps else 0,
            'active_clients': ClientCompany.objects.filter(id__in=client_ids, active=True).count() if 'clients.view' in caps else 0,
        })
    elif user.role == User.Role.WORKER:
        worker = user.worker_profile
        data.update({
            'current_worker_id': str(worker.id),
            'swap_candidates': [
                {'id': str(candidate.id), 'name': candidate.user.get_full_name() or candidate.user.email}
                for candidate in WorkerProfile.objects.filter(active=True).exclude(pk=worker.pk).select_related('user').order_by('user__first_name')
            ],
            'availabilities': AvailabilitySerializer(Availability.objects.filter(worker=worker).order_by('-starts_at')[:30], many=True).data,
            'swaps': [advanced_views._serialize_swap(item) for item in ShiftSwapRequest.objects.filter(Q(requested_by=worker) | Q(offered_to=worker)).select_related('shift__position', 'requested_by__user', 'offered_to__user').order_by('-created_at')[:30]],
            'upcoming_shifts': ShiftSerializer(Shift.objects.filter(Q(worker=worker) | Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED), starts_at__gte=now).distinct().order_by('starts_at')[:20], many=True).data,
        })
    else:
        companies = user.client_companies.all()
        company_ids = {str(pk) for pk in companies.values_list('pk', flat=True)}
        client_findings = advanced_views._schedule_findings()['coverage_gaps']
        data.update({
            'coverage_gaps': [item for item in client_findings if item.get('client') in company_ids],
            'contracts_due': Contract.objects.filter(client__in=companies, ends_on__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30))).count(),
            'documents': Document.objects.filter(client__in=companies).count(),
            'open_orders': ClientOrder.objects.filter(client__in=companies, status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING, ClientOrder.Status.CONFIRMED]).count(),
        })
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def schedule_quality(request):
    _require(request.user, 'schedule.view')
    try:
        date_from = advanced_views._as_dt(request.GET.get('date_from'), 'Von') if request.GET.get('date_from') else None
        date_to = advanced_views._as_dt(request.GET.get('date_to'), 'Bis') if request.GET.get('date_to') else None
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    return Response(_scoped_schedule_findings(request.user, date_from, date_to))


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def availability_delete(request, pk):
    try:
        item = Availability.objects.select_related('worker__user').get(pk=pk)
    except Availability.DoesNotExist:
        return Response({'detail': 'Eintrag wurde nicht gefunden.'}, status=404)
    if request.user.role == User.Role.WORKER:
        if item.worker.user_id != request.user.id:
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
    elif _is_manager(request.user):
        _require(request.user, 'schedule.edit')
        if not _is_admin(request.user) and not worker_in_scope(request.user, item.worker):
            return Response({'detail': 'Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
    else:
        return Response({'detail': 'Keine Berechtigung.'}, status=403)
    audit(request, 'availability.deleted', item)
    item.delete()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def bulk_publish(request):
    _require(request.user, 'schedule.publish')
    ids = request.data.get('ids') or []
    queryset = Shift.objects.filter(pk__in=ids, location__in=visible_locations(request.user)) if ids else Shift.objects.none()
    shifts = list(queryset.select_related('worker__user'))
    count = queryset.update(status=Shift.Status.PUBLISHED, published_at=timezone.now())
    for shift in shifts:
        if shift.worker_id:
            Notification.objects.get_or_create(
                user=shift.worker.user, kind=f'shift-published-{shift.id}',
                defaults={'title': 'Neue Schicht veröffentlicht', 'body': f'{shift.starts_at:%d.%m.%Y %H:%M}', 'action_url': '/schedule'},
            )
    audit(request, 'schedule.bulk_published', request.user, {'count': count})
    return Response({'published': count})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def folder_summary(request):
    user = request.user
    if _is_manager(user):
        if not has_capability(user, 'people.view') and not has_capability(user, 'clients.view'):
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        worker_scope = visible_workers(user, WorkerProfile.objects.filter(active=True)).select_related('user') if has_capability(user, 'people.view') else WorkerProfile.objects.none()
        locations = visible_locations(user)
        client_ids = list(locations.values_list('client_id', flat=True).distinct())
        client_scope = ClientCompany.objects.filter(id__in=client_ids, active=True) if has_capability(user, 'clients.view') else ClientCompany.objects.none()
        workers = [{
            'id': str(worker.id), 'name': worker.user.get_full_name() or worker.user.email, 'employee_number': worker.employee_number,
            'documents': Document.objects.filter(worker=worker).count(), 'contracts': Contract.objects.filter(worker=worker).count(),
            'payroll': PayrollStatement.objects.filter(worker=worker).count() if has_capability(user, 'payroll.view') else None,
        } for worker in worker_scope]
        clients = [{
            'id': str(client.id), 'name': client.name, 'customer_number': client.customer_number,
            'documents': Document.objects.filter(client=client).count(), 'contracts': Contract.objects.filter(client=client).count(),
            'orders': ClientOrder.objects.filter(client=client).count(),
        } for client in client_scope]
        return Response({'workers': workers, 'clients': clients})
    if user.role == User.Role.WORKER:
        worker = user.worker_profile
        return Response({'workers': [{
            'id': str(worker.id), 'name': worker.user.get_full_name() or worker.user.email, 'employee_number': worker.employee_number,
            'documents': Document.objects.filter(worker=worker).count(), 'contracts': Contract.objects.filter(worker=worker).count(),
            'payroll': PayrollStatement.objects.filter(worker=worker).count(),
        }], 'clients': []})
    clients = [{
        'id': str(client.id), 'name': client.name, 'customer_number': client.customer_number,
        'documents': Document.objects.filter(client=client).count(), 'contracts': Contract.objects.filter(client=client).count(),
        'orders': ClientOrder.objects.filter(client=client).count(),
    } for client in user.client_companies.filter(active=True)]
    return Response({'workers': [], 'clients': clients})


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def readiness(request):
    _require(request.user, 'workplace.manage')
    return Response(advanced_views._readiness())


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def import_contract_templates(request):
    _require(request.user, 'documents.manage')
    payload = request.data
    if request.FILES.get('file'):
        try:
            import json
            payload = json.loads(request.FILES['file'].read().decode('utf-8-sig'))
        except Exception as exc:
            return Response({'detail': f'Datei konnte nicht gelesen werden: {exc}'}, status=400)
    templates = payload if isinstance(payload, list) else payload.get('templates', [payload])
    valid_kinds = {value for value, _ in ContractTemplate.Kind.choices}
    created, updated, errors = 0, 0, []
    for index, item in enumerate(templates, start=1):
        try:
            name = str(item.get('name', '')).strip()
            kind = str(item.get('kind', '')).strip()
            version = str(item.get('version') or '1.0').strip()
            html_template = str(item.get('html_template', '')).strip()
            if not name or kind not in valid_kinds or not html_template:
                raise ValueError('name, gültiger kind und html_template sind erforderlich.')
            obj, was_created = ContractTemplate.objects.update_or_create(
                name=name, version=version,
                defaults={'kind': kind, 'schema': item.get('schema') or {}, 'html_template': html_template, 'active': bool(item.get('active', True))},
            )
            created += int(was_created)
            updated += int(not was_created)
            audit(request, 'contract_template.imported', obj)
        except Exception as exc:
            errors.append({'index': index, 'error': str(exc)})
    return Response({'created': created, 'updated': updated, 'errors': errors})


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def export_timesheets(request):
    _require(request.user, 'reports.view')
    _require(request.user, 'attendance.view')
    try:
        month_start, month_end = advanced_views._month_bounds(request.GET.get('month'))
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    qs = TimeEntry.objects.filter(
        worker__in=visible_workers(request.user),
        clock_in__gte=advanced_views._aware_start(month_start), clock_in__lt=advanced_views._aware_start(month_end),
    ).select_related('worker__user', 'shift__position').order_by('worker__employee_number', 'clock_in')
    if request.GET.get('worker'):
        qs = qs.filter(worker_id=request.GET['worker'])
    rows = [[
        entry.worker.employee_number,
        entry.worker.user.get_full_name() or entry.worker.user.email,
        entry.clock_in.astimezone().strftime('%d.%m.%Y %H:%M'),
        entry.clock_out.astimezone().strftime('%d.%m.%Y %H:%M') if entry.clock_out else '',
        entry.worked_minutes, 'Ja' if entry.approved else 'Nein', entry.shift.position.name if entry.shift_id else '', entry.edit_reason,
    ] for entry in qs]
    return advanced_views._csv_response(
        f'zeiterfassung-{month_start:%Y-%m}.csv',
        ['Personalnummer', 'Mitarbeiter', 'Beginn', 'Ende', 'Arbeitsminuten', 'Freigegeben', 'Position', 'Korrekturgrund'], rows,
    )


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def export_schedule(request):
    _require(request.user, 'reports.view')
    _require(request.user, 'schedule.view')
    try:
        date_from = advanced_views._as_date(request.GET.get('date_from') or timezone.localdate().isoformat(), 'Von')
        date_to = advanced_views._as_date(request.GET.get('date_to') or (date_from + timedelta(days=30)).isoformat(), 'Bis')
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    qs = Shift.objects.filter(
        location__in=visible_locations(request.user), starts_at__gte=advanced_views._aware_start(date_from),
        starts_at__lt=advanced_views._aware_start(date_to + timedelta(days=1)),
    ).select_related('worker__user', 'client', 'location', 'position').order_by('starts_at')
    rows = [[
        shift.starts_at.astimezone().strftime('%d.%m.%Y %H:%M'), shift.ends_at.astimezone().strftime('%d.%m.%Y %H:%M'),
        shift.client.name, shift.location.name, shift.position.name,
        shift.worker.user.get_full_name() if shift.worker_id else 'OpenShift', shift.get_status_display(), shift.break_minutes,
    ] for shift in qs]
    return advanced_views._csv_response(
        f'dienstplan-{date_from:%Y%m%d}-{date_to:%Y%m%d}.csv',
        ['Beginn', 'Ende', 'Kunde', 'Einsatzort', 'Position', 'Mitarbeiter', 'Status', 'Pause (Min.)'], rows,
    )


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def export_payroll_estimate(request):
    _require(request.user, 'payroll.export')
    _require(request.user, 'wage.view')
    try:
        month_start, month_end = advanced_views._month_bounds(request.GET.get('month'))
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    rows = []
    for worker in visible_workers(request.user, WorkerProfile.objects.filter(active=True)).select_related('user').order_by('employee_number'):
        if not can_view_wage(request.user, worker):
            continue
        entries = TimeEntry.objects.filter(
            worker=worker, approved=True,
            clock_in__gte=advanced_views._aware_start(month_start), clock_in__lt=advanced_views._aware_start(month_end),
        )
        minutes = sum(entry.worked_minutes for entry in entries)
        hours = Decimal(minutes) / Decimal(60)
        rate = worker.tariff_hourly_rate or Decimal('0')
        allowance = worker.extra_allowance or Decimal('0')
        estimate = hours * (rate + allowance)
        rows.append([
            worker.employee_number, worker.user.get_full_name() or worker.user.email,
            f'{hours.quantize(Decimal("0.01"))}', f'{rate.quantize(Decimal("0.01"))}',
            f'{allowance.quantize(Decimal("0.01"))}', f'{estimate.quantize(Decimal("0.01"))}',
            'Schätzung – keine steuerliche Lohnabrechnung',
        ])
    return advanced_views._csv_response(
        f'lohn-schaetzung-{month_start:%Y-%m}.csv',
        ['Personalnummer', 'Mitarbeiter', 'Freigegebene Stunden', 'Stundenlohn', 'Zulage je Stunde', 'Geschätztes Brutto', 'Hinweis'], rows,
    )
