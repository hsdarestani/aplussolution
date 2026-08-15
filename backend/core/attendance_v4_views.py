from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .attendance_models import TimeEntryCorrection
from .attendance_v4_models import (
    AttendanceAttestation,
    AttendanceBreak,
    AttendanceClockEvent,
    AttendanceNotice,
    AttendancePolicy,
    AttendanceTerminal,
)
from .attendance_v4_service import (
    attendance_policy_for_shift,
    break_summary,
    clock_in_worker,
    clock_out_worker,
    end_break,
    net_worked_minutes,
    scan_attendance_notices,
    start_break,
    submit_attestation,
)
from .models import Shift, TimeEntry, User, WorkerProfile
from .permissions import IsAdminOrManager
from .services import audit
from .shift_api import ShiftApiSerializer


MANAGER_ROLES = {User.Role.ADMIN, User.Role.MANAGER}


def _worker_name(worker):
    return worker.user.get_full_name() or worker.user.email


def _break_payload(item):
    return {
        'id': str(item.id),
        'status': item.status,
        'source': item.source,
        'paid': item.paid,
        'scheduled_minutes': item.scheduled_minutes,
        'started_at': item.started_at,
        'ended_at': item.ended_at,
        'actual_minutes': item.actual_minutes,
        'deductible_minutes': item.deductible_minutes,
        'note': item.note,
    }


def _entry_payload(entry, request=None):
    if not entry:
        return None
    summary = break_summary(entry)
    policy = attendance_policy_for_shift(entry.shift)
    return {
        'id': str(entry.id),
        'worker': str(entry.worker_id),
        'worker_name': _worker_name(entry.worker),
        'shift': str(entry.shift_id) if entry.shift_id else None,
        'shift_title': entry.shift.position.name if entry.shift_id else 'Arbeitszeit',
        'clock_in': entry.clock_in,
        'clock_out': entry.clock_out,
        'worked_minutes': net_worked_minutes(entry),
        'approved': entry.approved,
        'breaks': [_break_payload(item) for item in summary['rows']],
        'break_paid_minutes': summary['paid_minutes'],
        'break_unpaid_minutes': summary['unpaid_minutes'],
        'running_break': _break_payload(summary['running']) if summary['running'] else None,
        'planned_break': _break_payload(summary['planned']) if summary['planned'] else None,
        'attestation_required': {
            'break': bool(policy.break_attestation_required and not entry.attestations.filter(kind=AttendanceAttestation.Kind.BREAK).exists()),
            'end_of_shift': bool(policy.end_of_shift_attestation_required and not entry.attestations.filter(kind=AttendanceAttestation.Kind.END_OF_SHIFT).exists()),
        },
    }


def _policy_payload(policy):
    return {
        'id': str(policy.id) if policy.id else None,
        'name': policy.name,
        'location': str(policy.location_id) if policy.location_id else None,
        'active': policy.active,
        'priority': policy.priority,
        'early_clock_in_minutes': policy.early_clock_in_minutes,
        'early_clock_in_mode': policy.early_clock_in_mode,
        'late_clock_in_grace_minutes': policy.late_clock_in_grace_minutes,
        'early_clock_out_grace_minutes': policy.early_clock_out_grace_minutes,
        'late_clock_out_grace_minutes': policy.late_clock_out_grace_minutes,
        'no_show_after_minutes': policy.no_show_after_minutes,
        'missed_clock_out_after_minutes': policy.missed_clock_out_after_minutes,
        'clock_in_location_mode': policy.clock_in_location_mode,
        'clock_out_location_mode': policy.clock_out_location_mode,
        'allow_unscheduled_clock_in': policy.allow_unscheduled_clock_in,
        'required_break_after_minutes': policy.required_break_after_minutes,
        'required_break_minutes': policy.required_break_minutes,
        'default_break_paid': policy.default_break_paid,
        'auto_deduct_unpaid_breaks': policy.auto_deduct_unpaid_breaks,
        'break_attestation_required': policy.break_attestation_required,
        'end_of_shift_attestation_required': policy.end_of_shift_attestation_required,
        'terminal_photo_clock_in': policy.terminal_photo_clock_in,
        'terminal_photo_clock_out': policy.terminal_photo_clock_out,
    }


class AttendancePolicySerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = AttendancePolicy
        fields = '__all__'


class AttendancePolicyViewSet(viewsets.ModelViewSet):
    queryset = AttendancePolicy.objects.select_related('location').all()
    serializer_class = AttendancePolicySerializer
    permission_classes = [IsAdminOrManager]
    filterset_fields = ['active', 'location']
    ordering_fields = ['priority', 'updated_at']

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, 'attendance.policy_created', obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, 'attendance.policy_updated', obj)


class AttendanceNoticeSerializer(serializers.ModelSerializer):
    worker_name = serializers.SerializerMethodField()
    shift_title = serializers.CharField(source='shift.position.name', read_only=True)
    location_name = serializers.CharField(source='shift.location.name', read_only=True)

    class Meta:
        model = AttendanceNotice
        fields = '__all__'
        read_only_fields = [
            'worker', 'shift', 'entry', 'break_record', 'notice_type', 'severity', 'detected_at',
            'value_minutes', 'details', 'dedupe_key', 'resolved_by', 'resolved_at',
        ]

    def get_worker_name(self, obj):
        return _worker_name(obj.worker)


class AttendanceNoticeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AttendanceNotice.objects.select_related('worker__user', 'shift__position', 'shift__location', 'entry').all()
    serializer_class = AttendanceNoticeSerializer
    permission_classes = [IsAdminOrManager]
    filterset_fields = ['status', 'severity', 'notice_type', 'worker', 'shift']
    ordering_fields = ['detected_at', 'severity']

    def _set_state(self, request, obj, target):
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


class AttendanceTerminalSerializer(serializers.ModelSerializer):
    location_name = serializers.CharField(source='location.name', read_only=True)

    class Meta:
        model = AttendanceTerminal
        exclude = ['token_hash']
        read_only_fields = ['public_id', 'last_seen_at', 'created_by']


class AttendanceTerminalViewSet(viewsets.ModelViewSet):
    queryset = AttendanceTerminal.objects.select_related('location').all()
    serializer_class = AttendanceTerminalSerializer
    permission_classes = [IsAdminOrManager]
    filterset_fields = ['active', 'location']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = AttendanceTerminal.issue_token()
        terminal = serializer.save(token_hash=AttendanceTerminal.hash_token(token), created_by=request.user)
        audit(request, 'attendance.terminal_created', terminal)
        data = self.get_serializer(terminal).data
        data['terminal_token'] = token
        data['terminal_token_note'] = 'Dieses Secret wird nur einmal angezeigt.'
        return Response(data, status=201)

    @action(detail=True, methods=['post'], url_path='rotate-token')
    def rotate_token(self, request, pk=None):
        terminal = self.get_object()
        token = AttendanceTerminal.issue_token()
        terminal.token_hash = AttendanceTerminal.hash_token(token)
        terminal.save(update_fields=['token_hash', 'updated_at'])
        audit(request, 'attendance.terminal_token_rotated', terminal)
        return Response({'id': str(terminal.id), 'terminal_token': token, 'terminal_token_note': 'Dieses Secret wird nur einmal angezeigt.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def attendance_home_v4(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Diese Ansicht ist nur für Mitarbeiter.'}, status=403)
    worker = request.user.worker_profile
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    active = TimeEntry.objects.select_related('worker__user', 'shift__position', 'shift__location').prefetch_related(
        'attendance_breaks', 'attestations'
    ).filter(worker=worker, clock_out__isnull=True).order_by('-clock_in').first()
    history = list(TimeEntry.objects.select_related('worker__user', 'shift__position', 'shift__location').prefetch_related(
        'attendance_breaks', 'attestations'
    ).filter(worker=worker, clock_out__isnull=False).order_by('-clock_in')[:30])
    month_entries = list(TimeEntry.objects.select_related('shift').prefetch_related('attendance_breaks').filter(worker=worker, clock_in__gte=month_start))
    ownership = Q(slots__worker=worker, slots__status='claimed') | Q(worker=worker)
    eligible_shift = Shift.objects.filter(
        ownership,
        starts_at__lte=now + timezone.timedelta(hours=4),
        ends_at__gte=now - timezone.timedelta(hours=4),
        status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED],
    ).select_related('order', 'client', 'location', 'position').distinct().order_by('starts_at').first()
    corrections = TimeEntryCorrection.objects.select_related('entry', 'requested_by__user').filter(requested_by=worker).order_by('-created_at')[:20]
    policy = attendance_policy_for_shift(active.shift if active else eligible_shift)
    return Response({
        'active_entry': _entry_payload(active, request),
        'eligible_shift': ShiftApiSerializer(eligible_shift, context={'request': request}).data if eligible_shift else None,
        'policy': _policy_payload(policy),
        'month_worked_minutes': sum(net_worked_minutes(entry) for entry in month_entries),
        'pending_corrections': sum(item.status == TimeEntryCorrection.Status.PENDING for item in corrections),
        'history': [_entry_payload(entry, request) for entry in history],
        'corrections': [{
            'id': str(item.id), 'entry_id': str(item.entry_id), 'reason': item.reason, 'status': item.status,
            'created_at': item.created_at, 'decision_note': item.decision_note,
        } for item in corrections],
    })


@api_view(['POST'])
def break_start(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können eine Pause starten.'}, status=403)
    try:
        record = start_break(worker=request.user.worker_profile, request=request, method=AttendanceClockEvent.Method.MOBILE)
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=getattr(exc, 'status_code', 400))
    audit(request, 'attendance.break_started', record)
    return Response(_break_payload(record), status=201)


@api_view(['POST'])
def break_end(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können eine Pause beenden.'}, status=403)
    try:
        record = end_break(worker=request.user.worker_profile, request=request, method=AttendanceClockEvent.Method.MOBILE)
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=getattr(exc, 'status_code', 400))
    audit(request, 'attendance.break_ended', record)
    return Response(_break_payload(record))


@api_view(['POST'])
def attestation_submit(request, entry_id):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können eine Bestätigung abgeben.'}, status=403)
    entry = TimeEntry.objects.filter(pk=entry_id, worker=request.user.worker_profile).first()
    if not entry:
        return Response({'detail': 'Zeiteintrag wurde nicht gefunden.'}, status=404)
    try:
        obj = submit_attestation(
            entry=entry,
            worker=request.user.worker_profile,
            kind=str(request.data.get('kind') or AttendanceAttestation.Kind.END_OF_SHIFT),
            answers=request.data.get('answers') if isinstance(request.data.get('answers'), dict) else {},
            note=request.data.get('note', ''),
        )
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=getattr(exc, 'status_code', 400))
    audit(request, 'attendance.attestation_submitted', obj)
    return Response({'id': str(obj.id), 'entry': str(obj.entry_id), 'kind': obj.kind, 'answers': obj.answers, 'note': obj.note}, status=201)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def attendance_scan(request):
    result = scan_attendance_notices()
    audit(request, 'attendance.notice_scan', request.user, result)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def attendance_exceptions_v4(request):
    now = timezone.now()
    notices = AttendanceNotice.objects.select_related('worker__user', 'shift__position', 'shift__location').filter(
        status__in=[AttendanceNotice.Status.OPEN, AttendanceNotice.Status.ACKNOWLEDGED]
    ).order_by('severity', '-detected_at')[:200]
    unapproved = TimeEntry.objects.select_related('worker__user', 'shift__position').prefetch_related('attendance_breaks').filter(
        clock_out__isnull=False, approved=False
    ).order_by('-clock_in')[:100]
    long_running = TimeEntry.objects.select_related('worker__user', 'shift__position').prefetch_related('attendance_breaks').filter(
        clock_out__isnull=True, clock_in__lte=now - timezone.timedelta(hours=12)
    ).order_by('clock_in')[:100]
    corrections = TimeEntryCorrection.objects.select_related('entry', 'requested_by__user').filter(
        status=TimeEntryCorrection.Status.PENDING
    ).order_by('created_at')[:100]
    notice_data = AttendanceNoticeSerializer(notices, many=True).data
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
            'worker_name': _worker_name(item.requested_by), 'original_clock_in': item.entry.clock_in,
            'original_clock_out': item.entry.clock_out, 'requested_clock_in': item.requested_clock_in,
            'requested_clock_out': item.requested_clock_out, 'reason': item.reason, 'status': item.status,
            'created_at': item.created_at,
        } for item in corrections],
        'unapproved_entries': [_entry_payload(entry, request) for entry in unapproved],
        'long_running_entries': [_entry_payload(entry, request) for entry in long_running],
        'policies': AttendancePolicySerializer(AttendancePolicy.objects.select_related('location').all(), many=True).data,
        'terminals': AttendanceTerminalSerializer(AttendanceTerminal.objects.select_related('location').all(), many=True).data,
    })


def _terminal_worker(identity):
    text = str(identity or '').strip()
    if not text:
        return None
    return WorkerProfile.objects.select_related('user').filter(
        Q(employee_number__iexact=text) | Q(user__email__iexact=text), active=True, user__is_active=True
    ).first()


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
    photo = request.FILES.get('photo')
    lat, lng = terminal.location.latitude, terminal.location.longitude
    policy = attendance_policy_for_shift(location=terminal.location)
    if action_name == 'clock_in' and (terminal.photo_clock_in or policy.terminal_photo_clock_in) and not photo:
        return Response({'detail': 'Für das Einstempeln an diesem Terminal ist ein Foto erforderlich.'}, status=400)
    if action_name == 'clock_out' and (terminal.photo_clock_out or policy.terminal_photo_clock_out) and not photo:
        return Response({'detail': 'Für das Ausstempeln an diesem Terminal ist ein Foto erforderlich.'}, status=400)
    try:
        if action_name == 'clock_in':
            entry = clock_in_worker(worker=worker, shift_id=request.data.get('shift'), lat=lat, lng=lng, request=request, method=AttendanceClockEvent.Method.TERMINAL, photo=photo)
            payload = _entry_payload(entry, request)
        elif action_name == 'clock_out':
            entry, _ = clock_out_worker(worker=worker, lat=lat, lng=lng, request=request, method=AttendanceClockEvent.Method.TERMINAL, photo=photo, note=request.data.get('note', ''))
            payload = _entry_payload(entry, request)
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
    return Response({'terminal': str(terminal.public_id), 'worker_name': _worker_name(worker), 'action': action_name, 'result': payload}, status=201 if action_name == 'clock_in' else 200)
