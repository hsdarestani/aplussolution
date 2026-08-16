from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Shift, TimeOffRequest, User, WorkerProfile
from .permissions import IsAdminOrManager
from .self_service_models import (
    AvailabilityPreferenceSeries,
    OpenShiftPolicy,
    OpenShiftRequest,
    SelfServiceSettings,
    ShiftCoverageRequest,
    TimeOffRequestDetail,
    TimeOffType,
    UserSelfServicePreference,
)
from .self_service_service import (
    accept_coverage_request,
    cancel_coverage_request,
    cancel_open_shift_request,
    coworker_directory_for,
    create_coverage_request,
    create_detailed_time_off,
    decide_open_shift_request,
    decline_coverage_request,
    review_coverage_request,
    submit_open_shift_request,
    team_schedule_for,
    validate_availability_series,
    validate_series_change_cutoff,
    worker_can_access_open_shift,
)
from .services import audit
from .shift_slots import ShiftSlot
from .workplace_access import has_capability, location_in_scope, visible_locations, visible_workers


def _admin(user):
    return bool(user.role == User.Role.ADMIN or user.is_superuser)


def _manager_can(user, capability='schedule.edit'):
    return _admin(user) or (user.role == User.Role.MANAGER and has_capability(user, capability))


def _require_manager(user, capability='schedule.edit'):
    if not _manager_can(user, capability):
        raise PermissionDenied('Keine Berechtigung für diese Funktion.')


def _bool(value, default=False):
    if value is None:
        return default
    return value not in (False, 'false', '0', 0, '', None)


class SelfServiceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SelfServiceSettings
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_availability_notice_days(self, value):
        if value > 365:
            raise serializers.ValidationError('Maximal 365 Tage Vorlauf.')
        return value

    def validate_release_cutoff_hours(self, value):
        if value > 168:
            raise serializers.ValidationError('Freigabe-Vorlauf darf maximal 168 Stunden betragen.')
        return value

    def validate_drop_cutoff_hours(self, value):
        if value > 48:
            raise serializers.ValidationError('Drop-Vorlauf darf maximal 48 Stunden betragen.')
        return value

    def validate_swap_cutoff_hours(self, value):
        if value > 48:
            raise serializers.ValidationError('Swap-Vorlauf darf maximal 48 Stunden betragen.')
        return value


class UserSelfServicePreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSelfServicePreference
        fields = ['hide_contact_info', 'preferred_weekly_hours']


class AvailabilityPreferenceSeriesSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)

    class Meta:
        model = AvailabilityPreferenceSeries
        fields = '__all__'
        read_only_fields = ['created_by']
        extra_kwargs = {'worker': {'required': False}}

    def validate(self, attrs):
        validate_availability_series(attrs, actor=self.context['request'].user, instance=self.instance)
        return attrs


class TimeOffTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeOffType
        fields = '__all__'


class AvailabilityPreferenceSeriesViewSet(viewsets.ModelViewSet):
    queryset = AvailabilityPreferenceSeries.objects.select_related('worker__user', 'created_by').all()
    serializer_class = AvailabilityPreferenceSeriesSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset.filter(active=True)
        if _admin(user):
            return qs
        if user.role == User.Role.MANAGER:
            if not has_capability(user, 'schedule.view'):
                return qs.none()
            return qs.filter(worker__in=visible_workers(user)).distinct()
        if user.role == User.Role.WORKER:
            settings = SelfServiceSettings.load()
            if settings.show_availability_to_all:
                return qs
            return qs.filter(worker=user.worker_profile)
        return qs.none()

    def perform_create(self, serializer):
        user = self.request.user
        worker = serializer.validated_data.get('worker')
        if user.role == User.Role.WORKER:
            worker = user.worker_profile
        elif user.role == User.Role.MANAGER:
            _require_manager(user)
            if not worker or not visible_workers(user).filter(pk=worker.pk).exists():
                raise PermissionDenied('Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.')
        elif not _admin(user):
            raise PermissionDenied('Keine Berechtigung.')
        if not worker:
            raise ValidationError({'worker': 'Mitarbeiter ist erforderlich.'})
        obj = serializer.save(worker=worker, created_by=user)
        audit(self.request, 'self_service.availability.created', obj)

    def perform_update(self, serializer):
        user = self.request.user
        obj = serializer.instance
        if user.role == User.Role.WORKER:
            if obj.worker.user_id != user.id:
                raise PermissionDenied('Keine Berechtigung für diese Verfügbarkeit.')
            validate_series_change_cutoff(obj, user)
        elif user.role == User.Role.MANAGER:
            _require_manager(user)
            if not visible_workers(user).filter(pk=obj.worker_id).exists():
                raise PermissionDenied('Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.')
        elif not _admin(user):
            raise PermissionDenied('Keine Berechtigung.')
        updated = serializer.save()
        audit(self.request, 'self_service.availability.updated', updated)

    def perform_destroy(self, instance):
        user = self.request.user
        if user.role == User.Role.WORKER:
            if instance.worker.user_id != user.id:
                raise PermissionDenied('Keine Berechtigung für diese Verfügbarkeit.')
            validate_series_change_cutoff(instance, user)
        elif user.role == User.Role.MANAGER:
            _require_manager(user)
            if not visible_workers(user).filter(pk=instance.worker_id).exists():
                raise PermissionDenied('Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.')
        elif not _admin(user):
            raise PermissionDenied('Keine Berechtigung.')
        instance.active = False
        instance.save(update_fields=['active', 'updated_at'])
        audit(self.request, 'self_service.availability.archived', instance)


class TimeOffTypeViewSet(viewsets.ModelViewSet):
    queryset = TimeOffType.objects.all().order_by('name')
    serializer_class = TimeOffTypeSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset if _manager_can(self.request.user, 'attendance.view') else self.queryset.filter(active=True)

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'attendance.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=['active', 'updated_at'])
        audit(self.request, 'self_service.time_off_type.archived', instance)


def _serialize_coverage(obj):
    return {
        'id': str(obj.id),
        'kind': obj.kind,
        'status': obj.status,
        'shift': str(obj.shift_id),
        'shift_position': obj.shift.position.name,
        'shift_location': obj.shift.location.name,
        'shift_starts_at': obj.shift.starts_at,
        'requested_by': str(obj.requested_by_id),
        'requested_by_name': obj.requested_by.user.get_full_name() or obj.requested_by.user.email,
        'offered_to': str(obj.offered_to_id) if obj.offered_to_id else None,
        'offered_to_name': (obj.offered_to.user.get_full_name() or obj.offered_to.user.email) if obj.offered_to_id else None,
        'offered_shift': str(obj.offered_shift_id) if obj.offered_shift_id else None,
        'note': obj.note,
        'reviewed_at': obj.reviewed_at,
        'accepted_at': obj.accepted_at,
        'created_at': obj.created_at,
    }


def _serialize_open_request(obj):
    return {
        'id': str(obj.id),
        'shift': str(obj.shift_id),
        'position': obj.shift.position.name,
        'location': obj.shift.location.name,
        'starts_at': obj.shift.starts_at,
        'worker': str(obj.worker_id),
        'worker_name': obj.worker.user.get_full_name() or obj.worker.user.email,
        'status': obj.status,
        'note': obj.note,
        'decided_at': obj.decided_at,
        'created_at': obj.created_at,
    }


def _serialize_time_off(obj):
    try:
        detail = obj.self_service_detail
    except TimeOffRequestDetail.DoesNotExist:
        detail = None
    return {
        'id': str(obj.id),
        'worker': str(obj.worker_id),
        'worker_name': obj.worker.user.get_full_name() or obj.worker.user.email,
        'starts_on': obj.starts_on,
        'ends_on': obj.ends_on,
        'reason': obj.reason,
        'status': obj.status,
        'type': detail.time_off_type.code if detail else 'personal',
        'type_name': detail.time_off_type.name if detail else 'Persönlich',
        'all_day': detail.all_day if detail else True,
        'start_time': detail.start_time if detail else None,
        'end_time': detail.end_time if detail else None,
        'paid': detail.paid if detail else False,
        'paid_hours': detail.paid_hours if detail else None,
        'created_at': obj.created_at,
    }


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def self_service_settings(request):
    obj = SelfServiceSettings.load()
    if request.method == 'PATCH':
        _require_manager(request.user)
        serializer = SelfServiceSettingsSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(request, 'self_service.settings.updated', obj)
    return Response({**SelfServiceSettingsSerializer(obj).data, 'can_manage': _manager_can(request.user)})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def self_service_preference(request):
    obj, _ = UserSelfServicePreference.objects.get_or_create(user=request.user)
    if request.method == 'PATCH':
        if SelfServiceSettings.load().global_user_privacy and request.user.role == User.Role.WORKER and 'hide_contact_info' in request.data:
            return Response({'detail': 'Persönliche Datenschutzeinstellung wird global verwaltet.'}, status=403)
        serializer = UserSelfServicePreferenceSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(request, 'self_service.preference.updated', obj)
    return Response(UserSelfServicePreferenceSerializer(obj).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def coworkers(request):
    return Response(coworker_directory_for(request.user))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def team_schedule(request):
    start = parse_datetime(str(request.GET.get('starts_at') or ''))
    end = parse_datetime(str(request.GET.get('ends_at') or ''))
    if not start or not end or end <= start:
        return Response({'detail': 'starts_at und ends_at sind als gültiger Zeitraum erforderlich.'}, status=400)
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)
    return Response({'results': team_schedule_for(request.user, starts_at=start, ends_at=end)})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def open_shift_policy(request, shift_id):
    shift = Shift.objects.select_related('location', 'position').filter(pk=shift_id).first()
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    if request.user.role == User.Role.MANAGER and not location_in_scope(request.user, shift.location):
        return Response({'detail': 'Schicht liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
    if request.method == 'PATCH':
        _require_manager(request.user)
    policy, _ = OpenShiftPolicy.objects.get_or_create(shift=shift)
    if request.method == 'PATCH':
        audience_mode = request.data.get('audience_mode', policy.audience_mode)
        if audience_mode not in dict(OpenShiftPolicy.AudienceMode.choices):
            return Response({'detail': 'Ungültiger Zielgruppenmodus.'}, status=400)
        policy.require_approval = _bool(request.data.get('require_approval'), policy.require_approval)
        policy.audience_mode = audience_mode
        policy.updated_by = request.user
        policy.save(update_fields=['require_approval', 'audience_mode', 'updated_by', 'updated_at'])
        if 'selected_workers' in request.data:
            selected = WorkerProfile.objects.filter(pk__in=request.data.get('selected_workers') or [], active=True)
            if request.user.role == User.Role.MANAGER:
                allowed = visible_workers(request.user).filter(pk__in=selected.values_list('pk', flat=True))
                selected = allowed
            policy.selected_workers.set(selected)
        audit(request, 'self_service.open_shift_policy.updated', policy)
    return Response({
        'shift': str(shift.id),
        'require_approval': policy.require_approval,
        'audience_mode': policy.audience_mode,
        'selected_workers': [str(pk) for pk in policy.selected_workers.values_list('pk', flat=True)],
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def open_shift_requests(request):
    user = request.user
    if request.method == 'POST':
        if user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können OpenShift-Anfragen stellen.'}, status=403)
        shift = Shift.objects.select_related('location', 'position').filter(pk=request.data.get('shift')).first()
        if not shift:
            return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
        try:
            row, slot = submit_open_shift_request(user.worker_profile, shift, request.data.get('note', ''))
        except (ValidationError, PermissionDenied) as exc:
            detail = getattr(exc, 'detail', str(exc))
            if isinstance(detail, list):
                detail = detail[0]
            return Response({'detail': str(detail)}, status=403 if isinstance(exc, PermissionDenied) else 400)
        audit(request, 'self_service.open_shift.requested', row, {'claimed_slot': str(slot.id) if slot else None})
        return Response({**_serialize_open_request(row), 'claimed_slot': str(slot.id) if slot else None}, status=201 if slot else 202)
    qs = OpenShiftRequest.objects.select_related('shift__position', 'shift__location', 'worker__user').all()
    if user.role == User.Role.WORKER:
        qs = qs.filter(worker=user.worker_profile)
    elif user.role == User.Role.MANAGER:
        _require_manager(user, 'schedule.view')
        qs = qs.filter(shift__location__in=visible_locations(user)).distinct()
    elif not _admin(user):
        return Response({'results': []})
    return Response({'results': [_serialize_open_request(row) for row in qs[:200]]})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def open_shift_request_decide(request, pk):
    _require_manager(request.user)
    row = OpenShiftRequest.objects.select_related('shift__location').filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Bewerbung wurde nicht gefunden.'}, status=404)
    if request.user.role == User.Role.MANAGER and not location_in_scope(request.user, row.shift.location):
        return Response({'detail': 'Schicht liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
    try:
        decided, slot = decide_open_shift_request(row.id, manager=request.user, approve=_bool(request.data.get('approve')))
    except Exception as exc:
        detail = getattr(exc, 'detail', str(exc)); detail = detail[0] if isinstance(detail, list) else detail
        return Response({'detail': str(detail)}, status=400)
    audit(request, 'self_service.open_shift.decided', decided, {'slot': str(slot.id) if slot else None})
    return Response(_serialize_open_request(decided))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def open_shift_request_cancel(request, pk):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können eigene Bewerbungen zurückziehen.'}, status=403)
    row = OpenShiftRequest.objects.filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Bewerbung wurde nicht gefunden.'}, status=404)
    try:
        row = cancel_open_shift_request(row, request.user.worker_profile)
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=400)
    audit(request, 'self_service.open_shift.canceled', row)
    return Response(_serialize_open_request(row))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def coverage_requests(request):
    user = request.user
    if request.method == 'POST':
        if user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können Coverage-Anfragen erstellen.'}, status=403)
        shift = Shift.objects.select_related('position', 'location').filter(pk=request.data.get('shift')).first()
        if not shift:
            return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
        offered_to = WorkerProfile.objects.select_related('user').filter(pk=request.data.get('offered_to'), active=True).first() if request.data.get('offered_to') else None
        try:
            row = create_coverage_request(
                user.worker_profile,
                shift=shift,
                kind=str(request.data.get('kind') or ''),
                offered_to=offered_to,
                note=request.data.get('note', ''),
            )
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc)); detail = detail[0] if isinstance(detail, list) else detail
            return Response({'detail': str(detail)}, status=403 if isinstance(exc, PermissionDenied) else 400)
        audit(request, 'self_service.coverage.created', row)
        return Response(_serialize_coverage(row), status=201)
    qs = ShiftCoverageRequest.objects.select_related(
        'shift__position', 'shift__location', 'requested_by__user', 'offered_to__user', 'offered_shift'
    ).all()
    if user.role == User.Role.WORKER:
        qs = qs.filter(Q(requested_by=user.worker_profile) | Q(offered_to=user.worker_profile)).distinct()
    elif user.role == User.Role.MANAGER:
        _require_manager(user, 'schedule.view')
        qs = qs.filter(shift__location__in=visible_locations(user)).distinct()
    elif not _admin(user):
        return Response({'results': []})
    return Response({'results': [_serialize_coverage(row) for row in qs[:200]]})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def coverage_review(request, pk):
    _require_manager(request.user)
    row = ShiftCoverageRequest.objects.select_related('shift__location', 'shift__position', 'requested_by__user', 'offered_to__user').filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Coverage-Anfrage wurde nicht gefunden.'}, status=404)
    if request.user.role == User.Role.MANAGER and not location_in_scope(request.user, row.shift.location):
        return Response({'detail': 'Schicht liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
    offered_to = WorkerProfile.objects.select_related('user').filter(pk=request.data.get('offered_to'), active=True).first() if request.data.get('offered_to') else None
    if offered_to and request.user.role == User.Role.MANAGER and not visible_workers(request.user).filter(pk=offered_to.pk).exists():
        return Response({'detail': 'Zielmitarbeiter liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
    try:
        row = review_coverage_request(row, manager=request.user, approve=_bool(request.data.get('approve')), offered_to=offered_to)
    except Exception as exc:
        detail = getattr(exc, 'detail', str(exc)); detail = detail[0] if isinstance(detail, list) else detail
        return Response({'detail': str(detail)}, status=400)
    audit(request, 'self_service.coverage.reviewed', row)
    return Response(_serialize_coverage(row))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def coverage_accept(request, pk):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können eine Coverage-Anfrage annehmen.'}, status=403)
    offered_shift = Shift.objects.filter(pk=request.data.get('offered_shift')).first() if request.data.get('offered_shift') else None
    try:
        row = accept_coverage_request(pk, recipient=request.user.worker_profile, offered_shift=offered_shift)
    except ShiftCoverageRequest.DoesNotExist:
        return Response({'detail': 'Coverage-Anfrage wurde nicht gefunden.'}, status=404)
    except Exception as exc:
        detail = getattr(exc, 'detail', str(exc)); detail = detail[0] if isinstance(detail, list) else detail
        return Response({'detail': str(detail)}, status=400)
    audit(request, 'self_service.coverage.accepted', row)
    return Response(_serialize_coverage(row))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def coverage_decline(request, pk):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können eine Coverage-Anfrage ablehnen.'}, status=403)
    row = ShiftCoverageRequest.objects.select_related('shift__position', 'shift__location', 'requested_by__user', 'offered_to__user').filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Coverage-Anfrage wurde nicht gefunden.'}, status=404)
    try:
        row = decline_coverage_request(row, request.user.worker_profile)
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=400)
    audit(request, 'self_service.coverage.declined', row)
    return Response(_serialize_coverage(row))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def coverage_cancel(request, pk):
    row = ShiftCoverageRequest.objects.select_related('shift__position', 'shift__location', 'requested_by__user', 'offered_to__user').filter(pk=pk).first()
    if not row:
        return Response({'detail': 'Coverage-Anfrage wurde nicht gefunden.'}, status=404)
    try:
        row = cancel_coverage_request(row, request.user)
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=400)
    audit(request, 'self_service.coverage.canceled', row)
    return Response(_serialize_coverage(row))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def detailed_time_off(request):
    user = request.user
    if request.method == 'POST':
        worker = user.worker_profile if user.role == User.Role.WORKER else WorkerProfile.objects.select_related('user').filter(pk=request.data.get('worker')).first()
        if not worker:
            return Response({'detail': 'Mitarbeiter wurde nicht gefunden.'}, status=404)
        if user.role == User.Role.MANAGER:
            _require_manager(user, 'attendance.edit')
            if not visible_workers(user).filter(pk=worker.pk).exists():
                return Response({'detail': 'Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
        elif user.role not in {User.Role.WORKER, User.Role.ADMIN}:
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        type_obj = TimeOffType.objects.filter(code=request.data.get('type'), active=True).first()
        if not type_obj:
            return Response({'detail': 'Abwesenheitstyp wurde nicht gefunden.'}, status=404)
        starts_on = parse_date(str(request.data.get('starts_on') or ''))
        ends_on = parse_date(str(request.data.get('ends_on') or ''))
        if not starts_on or not ends_on:
            return Response({'detail': 'Start- und Enddatum sind erforderlich.'}, status=400)
        all_day = _bool(request.data.get('all_day'), True)
        start_time = parse_time(str(request.data.get('start_time') or '')) if not all_day else None
        end_time = parse_time(str(request.data.get('end_time') or '')) if not all_day else None
        try:
            obj = create_detailed_time_off(
                worker,
                actor=user,
                time_off_type=type_obj,
                starts_on=starts_on,
                ends_on=ends_on,
                reason=request.data.get('reason', ''),
                paid=_bool(request.data.get('paid')),
                paid_hours=request.data.get('paid_hours'),
                all_day=all_day,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc)); detail = detail[0] if isinstance(detail, list) else detail
            return Response({'detail': str(detail)}, status=403 if isinstance(exc, PermissionDenied) else 400)
        audit(request, 'self_service.time_off.created', obj)
        return Response(_serialize_time_off(obj), status=201)
    qs = TimeOffRequest.objects.select_related('worker__user', 'self_service_detail__time_off_type').all()
    if user.role == User.Role.WORKER:
        qs = qs.filter(worker=user.worker_profile)
    elif user.role == User.Role.MANAGER:
        _require_manager(user, 'attendance.view')
        qs = qs.filter(worker__in=visible_workers(user))
    elif not _admin(user):
        return Response({'results': []})
    return Response({'results': [_serialize_time_off(row) for row in qs[:200]]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def self_service_snapshot(request):
    settings = SelfServiceSettings.load()
    preference, _ = UserSelfServicePreference.objects.get_or_create(user=request.user)
    payload = {
        'settings': {**SelfServiceSettingsSerializer(settings).data, 'can_manage': _manager_can(request.user)},
        'preference': UserSelfServicePreferenceSerializer(preference).data,
        'time_off_types': TimeOffTypeSerializer(TimeOffType.objects.filter(active=True), many=True).data,
    }
    if request.user.role == User.Role.WORKER:
        worker = request.user.worker_profile
        payload['coverage_pending'] = ShiftCoverageRequest.objects.filter(
            Q(requested_by=worker) | Q(offered_to=worker),
            status__in=[ShiftCoverageRequest.Status.PENDING_REVIEW, ShiftCoverageRequest.Status.PENDING_ACCEPTANCE],
        ).distinct().count()
        payload['open_shift_requests_pending'] = OpenShiftRequest.objects.filter(worker=worker, status=OpenShiftRequest.Status.PENDING_APPROVAL).count()
    else:
        payload['coverage_pending'] = ShiftCoverageRequest.objects.filter(status=ShiftCoverageRequest.Status.PENDING_REVIEW).count()
        payload['open_shift_requests_pending'] = OpenShiftRequest.objects.filter(status=OpenShiftRequest.Status.PENDING_APPROVAL).count()
    return Response(payload)
