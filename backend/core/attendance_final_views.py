from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .absence_models import ShiftAbsenceCase
from .absence_service import report_absence
from .attendance_final_service import (
    client_ip,
    clock_event_audit,
    normalize_ip_networks,
    resolve_missing_clock_notices,
    scan_attendance_notices_final,
    validate_ip_policy,
)
from .attendance_models import TimeEntryCorrection
from .attendance_v4_models import AttendanceClockEvent, AttendanceNotice, AttendancePolicy, AttendanceTerminal
from .attendance_v4_service import (
    _assigned_shift,
    attendance_policy_for_shift,
    clock_in_worker,
    clock_out_worker,
    end_break,
    start_break,
)
from .attendance_v4_views import (
    AttendanceNoticeSerializer as BaseAttendanceNoticeSerializer,
    AttendancePolicyViewSet as BaseAttendancePolicyViewSet,
    AttendanceTerminalViewSet as BaseAttendanceTerminalViewSet,
    _break_payload,
    _entry_payload,
    _terminal_worker,
    _worker_name,
)
from .models import Notification, Shift, TimeEntry, User, WorkerProfile
from .permissions import IsAdminOrManager
from .services import audit
from .shift_slots import ShiftSlot
from .workplace_access import assignment_for, has_capability, location_in_scope, visible_locations, visible_workers


NOTICE_WINDOW_DAYS = 7


def _is_admin(user):
    return bool(user.role == User.Role.ADMIN or user.is_superuser)


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


def _notice_cutoff():
    return timezone.now() - timedelta(days=NOTICE_WINDOW_DAYS)


class FinalAttendancePolicySerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = AttendancePolicy
        fields = '__all__'

    def validate(self, attrs):
        mode = attrs.get('computer_ip_mode', getattr(self.instance, 'computer_ip_mode', AttendancePolicy.Enforcement.OFF))
        values = attrs.get('allowed_ip_networks', getattr(self.instance, 'allowed_ip_networks', []))
        attrs['allowed_ip_networks'] = validate_ip_policy(mode, values)
        return attrs


class FinalAttendancePolicyViewSet(BaseAttendancePolicyViewSet):
    serializer_class = FinalAttendancePolicySerializer

    def get_queryset(self):
        qs = AttendancePolicy.objects.select_related('location').all()
        user = self.request.user
        if _is_admin(user):
            return qs
        _require(user, 'attendance.view')
        return qs.filter(Q(location__isnull=True) | Q(location__in=visible_locations(user))).distinct()

    def _guard_location(self, serializer):
        user = self.request.user
        if _is_admin(user):
            return
        location = serializer.validated_data.get('location', getattr(serializer.instance, 'location', None))
        if location is None:
            if not _scope_is_all(user):
                raise PermissionDenied('Globale Attendance-Regeln dürfen nur mit betriebsweitem Zugriff verwaltet werden.')
            return
        if not location_in_scope(user, location):
            raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')

    def perform_create(self, serializer):
        _require(self.request.user, 'attendance.edit')
        self._guard_location(serializer)
        obj = serializer.save()
        audit(self.request, 'attendance.policy_created', obj)

    def perform_update(self, serializer):
        _require(self.request.user, 'attendance.edit')
        self._guard_location(serializer)
        obj = serializer.save()
        audit(self.request, 'attendance.policy_updated', obj)

    def perform_destroy(self, instance):
        _require(self.request.user, 'attendance.edit')
        if not _is_admin(self.request.user):
            if instance.location_id is None and not _scope_is_all(self.request.user):
                raise PermissionDenied('Globale Attendance-Regeln dürfen nicht gelöscht werden.')
            if instance.location_id and not location_in_scope(self.request.user, instance.location):
                raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')
        instance.delete()


class FinalAttendanceTerminalSerializer(serializers.ModelSerializer):
    location_name = serializers.SerializerMethodField()
    scope_label = serializers.CharField(source='get_scope_mode_display', read_only=True)

    class Meta:
        model = AttendanceTerminal
        exclude = ['token_hash']
        read_only_fields = ['public_id', 'last_seen_at', 'created_by']

    def get_location_name(self, obj):
        return obj.location.name if obj.location_id else 'Alle Einsatzpläne'

    def validate(self, attrs):
        scope_mode = attrs.get('scope_mode', getattr(self.instance, 'scope_mode', AttendanceTerminal.ScopeMode.LOCATION))
        location = attrs.get('location', getattr(self.instance, 'location', None))
        if scope_mode == AttendanceTerminal.ScopeMode.ALL:
            attrs['location'] = None
        elif not location:
            raise serializers.ValidationError({'location': 'Für einen festen Terminal-Einsatzplan ist ein Einsatzort erforderlich.'})
        return attrs


class FinalAttendanceTerminalViewSet(BaseAttendanceTerminalViewSet):
    serializer_class = FinalAttendanceTerminalSerializer

    def get_queryset(self):
        qs = AttendanceTerminal.objects.select_related('location').all()
        user = self.request.user
        if _is_admin(user):
            return qs
        _require(user, 'attendance.view')
        visible = Q(location__in=visible_locations(user))
        if _scope_is_all(user):
            visible |= Q(scope_mode=AttendanceTerminal.ScopeMode.ALL)
        return qs.filter(visible).distinct()

    def _guard_scope(self, serializer):
        user = self.request.user
        if _is_admin(user):
            return
        scope_mode = serializer.validated_data.get('scope_mode', getattr(serializer.instance, 'scope_mode', AttendanceTerminal.ScopeMode.LOCATION))
        location = serializer.validated_data.get('location', getattr(serializer.instance, 'location', None))
        if scope_mode == AttendanceTerminal.ScopeMode.ALL:
            if not _scope_is_all(user):
                raise PermissionDenied('Ein Terminal für alle Einsatzpläne erfordert betriebsweiten Zugriff.')
            return
        if not location or not location_in_scope(user, location):
            raise PermissionDenied('Terminal-Standort liegt außerhalb deines Verantwortungsbereichs.')

    def create(self, request, *args, **kwargs):
        _require(request.user, 'attendance.edit')
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._guard_scope(serializer)
        token = AttendanceTerminal.issue_token()
        terminal = serializer.save(token_hash=AttendanceTerminal.hash_token(token), created_by=request.user)
        audit(request, 'attendance.terminal_created', terminal, {'scope_mode': terminal.scope_mode})
        data = self.get_serializer(terminal).data
        data['terminal_token'] = token
        data['terminal_token_note'] = 'Dieses Secret wird nur einmal angezeigt.'
        return Response(data, status=201)

    def perform_update(self, serializer):
        _require(self.request.user, 'attendance.edit')
        self._guard_scope(serializer)
        terminal = serializer.save()
        audit(self.request, 'attendance.terminal_updated', terminal, {'scope_mode': terminal.scope_mode})

    def perform_destroy(self, instance):
        _require(self.request.user, 'attendance.edit')
        instance.delete()

    def rotate_token(self, request, pk=None):
        _require(request.user, 'attendance.edit')
        return super().rotate_token(request, pk=pk)


class FinalAttendanceNoticeViewSet(BaseAttendancePolicyViewSet):
    queryset = AttendanceNotice.objects.select_related('worker__user', 'shift__position', 'shift__location', 'entry').all()
    serializer_class = BaseAttendanceNoticeSerializer
    permission_classes = [IsAdminOrManager]
    filterset_fields = ['status', 'severity', 'notice_type', 'worker', 'shift']
    ordering_fields = ['detected_at', 'severity']

    def get_queryset(self):
        qs = self.queryset.filter(detected_at__gte=_notice_cutoff())
        user = self.request.user
        if _is_admin(user):
            return qs
        _require(user, 'attendance.view')
        return qs.filter(worker__in=visible_workers(user)).distinct()

    def _set_state(self, request, obj, target):
        _require(request.user, 'attendance.edit')
        if target not in {AttendanceNotice.Status.ACKNOWLEDGED, AttendanceNotice.Status.RESOLVED, AttendanceNotice.Status.DISMISSED}:
            return Response({'detail': 'Ungültiger Status.'}, status=400)
        obj.status = target
        if target in {AttendanceNotice.Status.RESOLVED, AttendanceNotice.Status.DISMISSED}:
            obj.resolved_by = request.user
            obj.resolved_at = timezone.now()
            obj.resolution_note = str(request.data.get('note') or '').strip()[:250]
        obj.save(update_fields=['status', 'resolved_by', 'resolved_at', 'resolution_note', 'updated_at'])
        audit(request, 'attendance.notice_updated', obj, {'status': target})
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        return self._set_state(request, self.get_object(), AttendanceNotice.Status.ACKNOWLEDGED)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        return self._set_state(request, self.get_object(), AttendanceNotice.Status.RESOLVED)

    @action(detail=True, methods=['post'])
    def dismiss(self, request, pk=None):
        return self._set_state(request, self.get_object(), AttendanceNotice.Status.DISMISSED)

    @action(detail=False, methods=['post'], url_path='clear-recent')
    def clear_recent(self, request):
        _require(request.user, 'attendance.edit')
        qs = self.get_queryset().filter(status__in=[AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED])
        count = qs.update(
            status=AttendanceNotice.Status.DISMISSED,
            resolved_by=request.user,
            resolved_at=timezone.now(),
            resolution_note='7-Tage-Ansicht geleert.',
        )
        audit(request, 'attendance.notices_cleared', request.user, {'count': count, 'window_days': NOTICE_WINDOW_DAYS})
        return Response({'cleared': count, 'window_days': NOTICE_WINDOW_DAYS})

    @action(detail=True, methods=['post'])
    def remind(self, request, pk=None):
        _require(request.user, 'attendance.edit')
        notice = self.get_object()
        Notification.objects.create(
            user=notice.worker.user,
            kind=f'attendance-reminder-{notice.id}-{timezone.now().timestamp()}',
            title='Zeiterfassung prüfen',
            body=f'{notice.get_notice_type_display()} · {notice.shift.position.name if notice.shift_id else "Arbeitszeit"}',
            action_url='/attendance',
        )
        audit(request, 'attendance.notice_reminder_sent', notice)
        return Response({'sent': True})

    @action(detail=True, methods=['post'], url_path='report-absence')
    def report_absence_action(self, request, pk=None):
        _require(request.user, 'attendance.edit')
        notice = self.get_object()
        if not notice.shift_id:
            return Response({'detail': 'Für diesen Hinweis ist keine Schicht hinterlegt.'}, status=400)
        slot = ShiftSlot.objects.filter(
            shift=notice.shift,
            worker=notice.worker,
            status=ShiftSlot.Status.CLAIMED,
        ).first()
        if not slot:
            return Response({'detail': 'Der zugehörige Personalplatz wurde nicht gefunden.'}, status=409)
        existing = ShiftAbsenceCase.objects.filter(
            slot=slot,
            status__in=[
                ShiftAbsenceCase.Status.REPORTED,
                ShiftAbsenceCase.Status.COVERAGE_PENDING,
                ShiftAbsenceCase.Status.OFFERED,
                ShiftAbsenceCase.Status.MOVED_TO_OPEN,
            ],
        ).first()
        if existing:
            return Response({'id': str(existing.id), 'status': existing.status, 'existing': True})
        case = report_absence(
            shift=notice.shift,
            absent_worker=notice.worker,
            reported_by=request.user,
            kind=ShiftAbsenceCase.Kind.NO_SHOW if notice.notice_type == AttendanceNotice.Type.NO_SHOW else ShiftAbsenceCase.Kind.OTHER,
            note=str(request.data.get('note') or 'Aus Attendance Notice gemeldet.'),
            source=ShiftAbsenceCase.Source.MANAGER,
            slot_id=slot.id,
        )
        audit(request, 'attendance.notice_absence_reported', notice, {'absence_case': str(case.id)})
        return Response({'id': str(case.id), 'status': case.status, 'existing': False}, status=201)

    @action(detail=True, methods=['post'], url_path='create-time-entry')
    def create_time_entry(self, request, pk=None):
        _require(request.user, 'attendance.edit')
        notice = self.get_object()
        raw_in = request.data.get('clock_in')
        raw_out = request.data.get('clock_out')
        clock_in = parse_datetime(str(raw_in)) if raw_in else None
        clock_out = parse_datetime(str(raw_out)) if raw_out else None
        if not clock_in:
            return Response({'detail': 'Gültiger Beginn ist erforderlich.'}, status=400)
        if timezone.is_naive(clock_in):
            clock_in = timezone.make_aware(clock_in, timezone.get_current_timezone())
        if clock_out and timezone.is_naive(clock_out):
            clock_out = timezone.make_aware(clock_out, timezone.get_current_timezone())
        if clock_out and clock_out <= clock_in:
            return Response({'detail': 'Ende muss nach dem Beginn liegen.'}, status=400)
        if notice.shift_id and TimeEntry.objects.filter(worker=notice.worker, shift=notice.shift).exists():
            return Response({'detail': 'Für diese Schicht besteht bereits ein Zeiteintrag.'}, status=409)
        entry = TimeEntry.objects.create(
            worker=notice.worker,
            shift=notice.shift,
            clock_in=clock_in,
            clock_out=clock_out,
            edit_reason=str(request.data.get('reason') or 'Manuell aus Attendance Notice erstellt.'),
        )
        ip = client_ip(request)
        AttendanceClockEvent.objects.create(
            entry=entry,
            kind=AttendanceClockEvent.Kind.CLOCK_IN,
            method=AttendanceClockEvent.Method.MANAGER,
            occurred_at=clock_in,
            ip_address=ip,
            metadata={'source': 'attendance_notice', 'notice_id': str(notice.id)},
        )
        if clock_out:
            AttendanceClockEvent.objects.create(
                entry=entry,
                kind=AttendanceClockEvent.Kind.CLOCK_OUT,
                method=AttendanceClockEvent.Method.MANAGER,
                occurred_at=clock_out,
                ip_address=ip,
                metadata={'source': 'attendance_notice', 'notice_id': str(notice.id)},
            )
        resolve_missing_clock_notices(notice.worker, notice.shift, entry=entry)
        if notice.status in [AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED]:
            notice.status = AttendanceNotice.Status.RESOLVED
            notice.resolved_by = request.user
            notice.resolved_at = timezone.now()
            notice.resolution_note = 'Manueller Zeiteintrag erstellt.'
            notice.entry = entry
            notice.save(update_fields=['status', 'resolved_by', 'resolved_at', 'resolution_note', 'entry', 'updated_at'])
        audit(request, 'attendance.notice_time_entry_created', entry, {'notice': str(notice.id)})
        return Response(_entry_with_audit(entry, request), status=201)


def _entry_with_audit(entry, request=None):
    payload = _entry_payload(entry, request)
    payload.update(clock_event_audit(entry))
    return payload


def _assigned_terminal_shift(worker, terminal, shift_id=None, now=None):
    now = now or timezone.now()
    if terminal.scope_mode == AttendanceTerminal.ScopeMode.ALL:
        return _assigned_shift(worker, shift_id=shift_id, now=now)
    ownership = Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=worker)
    qs = Shift.objects.filter(
        ownership,
        location=terminal.location,
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
    ).select_related('location', 'position').distinct()
    if shift_id:
        return qs.filter(pk=shift_id).first()
    return qs.filter(
        starts_at__lte=now + timedelta(hours=4),
        ends_at__gte=now - timedelta(hours=4),
    ).order_by('starts_at').first()


@api_view(['POST'])
@permission_classes([AllowAny])
def terminal_clock(request, public_id):
    terminal = AttendanceTerminal.objects.select_related('location').filter(public_id=public_id, active=True).first()
    if not terminal:
        return Response({'detail': 'Terminal wurde nicht gefunden.'}, status=404)
    token = request.headers.get('X-Terminal-Token') or request.data.get('terminal_token')
    if not terminal.token_matches(token):
        return Response({'detail': 'Terminal-Authentifizierung fehlgeschlagen.'}, status=403)
    worker = _terminal_worker(request.data.get('identity'))
    if not worker:
        return Response({'detail': 'Mitarbeiter wurde nicht gefunden.'}, status=404)
    action_name = str(request.data.get('action') or '').lower()
    shift = _assigned_terminal_shift(worker, terminal, shift_id=request.data.get('shift'))
    if action_name == 'clock_in' and not shift:
        return Response({'detail': 'Für dieses Terminal wurde keine passende Schicht gefunden.'}, status=400)
    if terminal.scope_mode == AttendanceTerminal.ScopeMode.LOCATION and shift and shift.location_id != terminal.location_id:
        return Response({'detail': 'Diese Schicht gehört nicht zum Einsatzplan dieses Terminals.'}, status=403)
    photo = request.FILES.get('photo')
    policy = attendance_policy_for_shift(shift=shift, location=terminal.location)
    if action_name == 'clock_in' and (terminal.photo_clock_in or policy.terminal_photo_clock_in) and not photo:
        return Response({'detail': 'Für das Einstempeln an diesem Terminal ist ein Foto erforderlich.'}, status=400)
    if action_name == 'clock_out' and (terminal.photo_clock_out or policy.terminal_photo_clock_out) and not photo:
        return Response({'detail': 'Für das Ausstempeln an diesem Terminal ist ein Foto erforderlich.'}, status=400)
    try:
        if action_name == 'clock_in':
            # Terminals are trusted kiosk devices. Use the selected shift coordinates so
            # personal-device geofence/IP rules do not block a terminal clock action.
            lat = shift.location.latitude if shift and shift.location_id else None
            lng = shift.location.longitude if shift and shift.location_id else None
            entry = clock_in_worker(
                worker=worker,
                shift_id=shift.id if shift else None,
                lat=lat,
                lng=lng,
                request=request,
                method=AttendanceClockEvent.Method.TERMINAL,
                photo=photo,
            )
            resolve_missing_clock_notices(worker, entry.shift, entry=entry)
            payload = _entry_with_audit(entry, request)
        elif action_name == 'clock_out':
            active = TimeEntry.objects.select_related('shift__location').filter(worker=worker, clock_out__isnull=True).order_by('-clock_in').first()
            if not active:
                return Response({'detail': 'Keine laufende Zeiterfassung gefunden.'}, status=400)
            if terminal.scope_mode == AttendanceTerminal.ScopeMode.LOCATION and active.shift_id and active.shift.location_id != terminal.location_id:
                return Response({'detail': 'Der laufende Zeiteintrag gehört zu einem anderen Einsatzplan.'}, status=403)
            lat = active.shift.location.latitude if active.shift_id else None
            lng = active.shift.location.longitude if active.shift_id else None
            entry, _ = clock_out_worker(
                worker=worker,
                lat=lat,
                lng=lng,
                request=request,
                method=AttendanceClockEvent.Method.TERMINAL,
                photo=photo,
                note=request.data.get('note', ''),
            )
            payload = _entry_with_audit(entry, request)
        elif action_name == 'break_start':
            payload = _break_payload(start_break(worker=worker, request=None, method=AttendanceClockEvent.Method.TERMINAL))
        elif action_name == 'break_end':
            payload = _break_payload(end_break(worker=worker, request=None, method=AttendanceClockEvent.Method.TERMINAL))
        else:
            return Response({'detail': 'Ungültige Terminal-Aktion.'}, status=400)
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=getattr(exc, 'status_code', 400))
    terminal.last_seen_at = timezone.now()
    terminal.save(update_fields=['last_seen_at', 'updated_at'])
    return Response({
        'terminal': str(terminal.public_id),
        'terminal_scope': terminal.scope_mode,
        'worker_name': _worker_name(worker),
        'action': action_name,
        'result': payload,
    }, status=201 if action_name == 'clock_in' else 200)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def attendance_scan(request):
    _require(request.user, 'attendance.edit')
    if not _scope_is_all(request.user):
        return Response({'detail': 'Der globale Attendance-Scan ist nur mit betriebsweitem Zugriff verfügbar.'}, status=403)
    result = scan_attendance_notices_final()
    audit(request, 'attendance.notice_scan', request.user, result)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def attendance_exceptions(request):
    _require(request.user, 'attendance.view')
    now = timezone.now()
    worker_ids = _visible_worker_ids(request.user)
    locations = visible_locations(request.user)
    cutoff = _notice_cutoff()
    notices = AttendanceNotice.objects.select_related('worker__user', 'shift__position', 'shift__location', 'entry').filter(
        worker_id__in=worker_ids,
        detected_at__gte=cutoff,
        status__in=[AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED],
    ).order_by('-detected_at')[:200]
    unapproved = TimeEntry.objects.select_related('worker__user', 'shift__position', 'shift__location').prefetch_related('attendance_breaks', 'clock_events').filter(
        worker_id__in=worker_ids, clock_out__isnull=False, approved=False
    ).order_by('-clock_in')[:100]
    long_running = TimeEntry.objects.select_related('worker__user', 'shift__position', 'shift__location').prefetch_related('attendance_breaks', 'clock_events').filter(
        worker_id__in=worker_ids, clock_out__isnull=True, clock_in__lte=now - timedelta(hours=12)
    ).order_by('clock_in')[:100]
    corrections = TimeEntryCorrection.objects.select_related('entry', 'requested_by__user').filter(
        requested_by_id__in=worker_ids, status=TimeEntryCorrection.Status.PENDING
    ).order_by('created_at')[:100]
    notice_data = BaseAttendanceNoticeSerializer(notices, many=True).data
    policies = AttendancePolicy.objects.select_related('location').filter(Q(location__isnull=True) | Q(location__in=locations)).distinct()
    terminals = AttendanceTerminal.objects.select_related('location')
    if not _is_admin(request.user):
        terminal_scope = Q(location__in=locations)
        if _scope_is_all(request.user):
            terminal_scope |= Q(scope_mode=AttendanceTerminal.ScopeMode.ALL)
        terminals = terminals.filter(terminal_scope).distinct()
    return Response({
        'notice_window_days': NOTICE_WINDOW_DAYS,
        'notice_window_start': cutoff,
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
            'id': str(item.id),
            'entry_id': str(item.entry_id),
            'worker_id': str(item.requested_by_id),
            'worker_name': _worker_name(item.requested_by),
            'original_clock_in': item.entry.clock_in,
            'original_clock_out': item.entry.clock_out,
            'requested_clock_in': item.requested_clock_in,
            'requested_clock_out': item.requested_clock_out,
            'reason': item.reason,
            'status': item.status,
            'created_at': item.created_at,
        } for item in corrections],
        'unapproved_entries': [_entry_with_audit(entry, request) for entry in unapproved],
        'long_running_entries': [_entry_with_audit(entry, request) for entry in long_running],
        'policies': FinalAttendancePolicySerializer(policies, many=True).data,
        'terminals': FinalAttendanceTerminalSerializer(terminals, many=True).data,
    })
