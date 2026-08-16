from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Shift, User
from .permissions import IsAdminOrManager
from .scheduler_completion_models import (
    ScheduleAnnotation,
    ScheduleTask,
    ScheduleTaskList,
    SchedulerDisplayPreference,
)
from .scheduler_completion_service import (
    annotation_applies_to_worker,
    apply_business_closed_action,
    confirm_shift_slot,
    pending_confirmations_for_worker,
)
from .scheduling_models import ScheduleGroup, ScheduleMembership
from .services import audit
from .shift_slots import ShiftSlot
from .workplace_access import has_capability, location_in_scope, visible_locations
from .workplace_models import WorkplaceSettings


def _admin(user):
    return bool(user.role == User.Role.ADMIN or user.is_superuser)


def _require(user, capability):
    if not _admin(user) and not has_capability(user, capability):
        raise PermissionDenied('Keine Berechtigung für diese Funktion.')


def _validate_timezone(value):
    try:
        ZoneInfo(str(value))
    except Exception as exc:
        raise serializers.ValidationError('Ungültige IANA-Zeitzone.') from exc
    return value


def _worker_visible_task_ids(worker, task_lists):
    """Return task IDs a worker can see/complete without leaking sibling assignments."""
    list_rows = list(task_lists.values('id', 'work_date'))
    if not list_rows:
        return []
    dates = {row['work_date'] for row in list_rows}
    list_dates = {row['id']: row['work_date'] for row in list_rows}
    position_days = set(
        Shift.objects.filter(
            slots__worker=worker,
            slots__status=ShiftSlot.Status.CLAIMED,
            starts_at__date__in=dates,
        ).exclude(status=Shift.Status.CANCELLED)
        .values_list('starts_at__date', 'position_id')
    )
    task_rows = ScheduleTask.objects.filter(task_list_id__in=list_dates).values(
        'id', 'task_list_id', 'assignee_id', 'position_id'
    )
    allowed = []
    for row in task_rows:
        if row['assignee_id'] == worker.id:
            allowed.append(row['id'])
            continue
        if row['assignee_id'] is not None:
            continue
        if row['position_id'] is None or (list_dates[row['task_list_id']], row['position_id']) in position_days:
            allowed.append(row['id'])
    return allowed


def _tasks_for_serializer(obj, request):
    qs = obj.tasks.select_related('assignee__user', 'position', 'completed_by').all()
    user = getattr(request, 'user', None) if request else None
    if not user or not user.is_authenticated or user.role != User.Role.WORKER:
        return qs
    allowed_ids = _worker_visible_task_ids(user.worker_profile, ScheduleTaskList.objects.filter(pk=obj.pk))
    return qs.filter(pk__in=allowed_ids)


class ScheduleAnnotationSerializer(serializers.ModelSerializer):
    schedule_name = serializers.CharField(source='schedule.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleAnnotation
        fields = '__all__'
        read_only_fields = ['created_by']

    def get_created_by_name(self, obj):
        return (obj.created_by.get_full_name() or obj.created_by.email) if obj.created_by_id else ''

    def validate(self, attrs):
        start = attrs.get('starts_on', getattr(self.instance, 'starts_on', None))
        end = attrs.get('ends_on', getattr(self.instance, 'ends_on', None))
        if start and end and end < start:
            raise serializers.ValidationError({'ends_on': 'Enddatum darf nicht vor dem Startdatum liegen.'})
        return attrs


class ScheduleTaskSerializer(serializers.ModelSerializer):
    assignee_name = serializers.CharField(source='assignee.user.get_full_name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)
    completed_by_name = serializers.SerializerMethodField()
    completed = serializers.BooleanField(read_only=True)

    class Meta:
        model = ScheduleTask
        fields = '__all__'
        read_only_fields = ['completed_at', 'completed_by']

    def get_completed_by_name(self, obj):
        return (obj.completed_by.get_full_name() or obj.completed_by.email) if obj.completed_by_id else ''


class ScheduleTaskListSerializer(serializers.ModelSerializer):
    schedule_name = serializers.CharField(source='schedule.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    tasks = serializers.SerializerMethodField()
    completed_count = serializers.SerializerMethodField()
    task_count = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleTaskList
        fields = '__all__'
        read_only_fields = ['created_by']

    def _tasks(self, obj):
        return list(_tasks_for_serializer(obj, self.context.get('request')))

    def get_tasks(self, obj):
        return ScheduleTaskSerializer(self._tasks(obj), many=True, context=self.context).data

    def get_completed_count(self, obj):
        return sum(1 for task in self._tasks(obj) if task.completed_at)

    def get_task_count(self, obj):
        return len(self._tasks(obj))


class SchedulerDisplayPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchedulerDisplayPreference
        fields = ['color_mode', 'timezone_mode', 'local_timezone']

    def validate_local_timezone(self, value):
        return _validate_timezone(value)


class ScheduleAnnotationViewSet(viewsets.ModelViewSet):
    queryset = ScheduleAnnotation.objects.all()
    serializer_class = ScheduleAnnotationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset.filter(active=True).select_related('schedule', 'location', 'created_by').prefetch_related('schedule__locations')
        starts_on = parse_date(str(self.request.GET.get('starts_on') or ''))
        ends_on = parse_date(str(self.request.GET.get('ends_on') or ''))
        if starts_on:
            qs = qs.filter(ends_on__gte=starts_on)
        if ends_on:
            qs = qs.filter(starts_on__lte=ends_on)
        if _admin(user):
            return qs
        if user.role == User.Role.MANAGER:
            _require(user, 'schedule.view')
            locations = visible_locations(user)
            schedule_ids = ScheduleGroup.objects.filter(active=True, locations__in=locations).values_list('id', flat=True)
            return qs.filter(
                Q(location__isnull=True, schedule__isnull=True)
                | Q(location__in=locations)
                | Q(schedule_id__in=schedule_ids)
            ).distinct()
        if user.role == User.Role.WORKER:
            worker = user.worker_profile
            rows = [obj.pk for obj in qs if annotation_applies_to_worker(obj, worker)]
            return qs.filter(pk__in=rows)
        return qs.none()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'schedule.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def _validate_scope(self, serializer):
        user = self.request.user
        if _admin(user):
            return
        _require(user, 'schedule.edit')
        location = serializer.validated_data.get('location', getattr(serializer.instance, 'location', None))
        schedule = serializer.validated_data.get('schedule', getattr(serializer.instance, 'schedule', None))
        if location and not location_in_scope(user, location):
            raise PermissionDenied('Einsatzort liegt außerhalb deines Verantwortungsbereichs.')
        if schedule and any(not location_in_scope(user, loc) for loc in schedule.locations.all()):
            raise PermissionDenied('Dienstplan enthält Einsatzorte außerhalb deines Verantwortungsbereichs.')

    def perform_create(self, serializer):
        self._validate_scope(serializer)
        obj = serializer.save(created_by=self.request.user)
        result = apply_business_closed_action(obj)
        audit(self.request, 'schedule.annotation.created', obj, {'business_closed_result': result})
        self._business_closed_result = result

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if hasattr(self, '_business_closed_result'):
            response.data['business_closed_result'] = self._business_closed_result
        return response

    def perform_update(self, serializer):
        self._validate_scope(serializer)
        obj = serializer.save()
        audit(self.request, 'schedule.annotation.updated', obj)

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=['active', 'updated_at'])
        audit(self.request, 'schedule.annotation.archived', instance)


class ScheduleTaskListViewSet(viewsets.ModelViewSet):
    queryset = ScheduleTaskList.objects.all()
    serializer_class = ScheduleTaskListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = self.queryset.filter(active=True).select_related('schedule', 'location', 'created_by').prefetch_related(
            'tasks__assignee__user', 'tasks__position', 'tasks__completed_by'
        )
        date_value = parse_date(str(self.request.GET.get('date') or ''))
        if date_value:
            qs = qs.filter(work_date=date_value)
        if _admin(user):
            return qs
        if user.role == User.Role.MANAGER:
            _require(user, 'schedule.view')
            locations = visible_locations(user)
            schedule_ids = ScheduleGroup.objects.filter(active=True, locations__in=locations).values_list('id', flat=True)
            return qs.filter(
                Q(location__isnull=True, schedule__isnull=True)
                | Q(location__in=locations)
                | Q(schedule_id__in=schedule_ids)
            ).distinct()
        if user.role == User.Role.WORKER:
            worker = user.worker_profile
            schedule_ids = ScheduleMembership.objects.filter(worker=worker, active=True).values_list('schedule_id', flat=True)
            location_ids = ScheduleMembership.objects.filter(worker=worker, active=True).values_list('schedule__locations', flat=True)
            shift_locations = Shift.objects.filter(
                slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED
            ).values_list('location_id', flat=True)
            return qs.filter(
                Q(schedule__isnull=True, location__isnull=True)
                | Q(schedule_id__in=schedule_ids)
                | Q(location_id__in=location_ids)
                | Q(location_id__in=shift_locations)
            ).distinct()
        return qs.none()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'schedule.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        user = self.request.user
        if not _admin(user):
            _require(user, 'schedule.edit')
            location = serializer.validated_data.get('location')
            schedule = serializer.validated_data.get('schedule')
            if location and not location_in_scope(user, location):
                raise PermissionDenied('Einsatzort liegt außerhalb deines Verantwortungsbereichs.')
            if schedule and any(not location_in_scope(user, loc) for loc in schedule.locations.all()):
                raise PermissionDenied('Dienstplan enthält Einsatzorte außerhalb deines Verantwortungsbereichs.')
        obj = serializer.save(created_by=user)
        audit(self.request, 'schedule.task_list.created', obj)

    def perform_destroy(self, instance):
        instance.active = False
        instance.save(update_fields=['active', 'updated_at'])
        audit(self.request, 'schedule.task_list.archived', instance)


class ScheduleTaskViewSet(viewsets.ModelViewSet):
    queryset = ScheduleTask.objects.all()
    serializer_class = ScheduleTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        allowed_lists = ScheduleTaskListViewSet()
        allowed_lists.request = self.request
        list_qs = allowed_lists.get_queryset()
        qs = self.queryset.filter(task_list__in=list_qs).select_related(
            'task_list', 'assignee__user', 'position', 'completed_by'
        )
        user = self.request.user
        if user.role == User.Role.WORKER:
            qs = qs.filter(pk__in=_worker_visible_task_ids(user.worker_profile, list_qs))
        return qs

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'schedule.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        task_list = serializer.validated_data['task_list']
        user = self.request.user
        if user.role == User.Role.MANAGER:
            _require(user, 'schedule.edit')
            if task_list.location_id and not location_in_scope(user, task_list.location):
                raise PermissionDenied('Aufgabenliste liegt außerhalb deines Verantwortungsbereichs.')
            if task_list.schedule_id and any(not location_in_scope(user, loc) for loc in task_list.schedule.locations.all()):
                raise PermissionDenied('Aufgabenliste liegt außerhalb deines Verantwortungsbereichs.')
        obj = serializer.save()
        audit(self.request, 'schedule.task.created', obj)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        task = self.get_object()
        if request.user.role == User.Role.WORKER:
            worker = request.user.worker_profile
            if task.assignee_id and task.assignee_id != worker.id:
                return Response({'detail': 'Diese Aufgabe ist einem anderen Mitarbeiter zugewiesen.'}, status=403)
        elif request.user.role == User.Role.MANAGER:
            _require(request.user, 'schedule.edit')
        elif not _admin(request.user):
            return Response({'detail': 'Keine Berechtigung für diese Aufgabe.'}, status=403)
        completed = request.data.get('completed', True) not in (False, 'false', '0', 0)
        task.completed_at = timezone.now() if completed else None
        task.completed_by = request.user if completed else None
        task.save(update_fields=['completed_at', 'completed_by', 'updated_at'])
        audit(request, 'schedule.task.completed' if completed else 'schedule.task.reopened', task)
        return Response(self.get_serializer(task).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def shift_confirmations(request):
    if request.user.role != User.Role.WORKER:
        return Response({'results': [], 'pending_count': 0})
    rows = pending_confirmations_for_worker(request.user.worker_profile)
    data = [{
        'id': str(item.id),
        'slot': str(item.slot_id),
        'shift': str(item.shift_id),
        'position': item.shift.position.name,
        'location': item.shift.location.name,
        'starts_at': item.shift.starts_at,
        'ends_at': item.shift.ends_at,
        'status': item.status,
        'requested_at': item.requested_at,
        'confirmed_at': item.confirmed_at,
    } for item in rows]
    return Response({'results': data, 'pending_count': len(data)})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def shift_confirm(request, slot_id):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Nur Mitarbeiter können Schichten bestätigen.'}, status=403)
    try:
        confirmation = confirm_shift_slot(request.user.worker_profile, slot_id, request.user)
    except ValidationError as exc:
        detail = exc.detail[0] if isinstance(exc.detail, list) else exc.detail
        return Response({'detail': str(detail)}, status=400)
    audit(request, 'shift.confirmed_by_worker', confirmation.shift, {'slot': str(slot_id)})
    return Response({'slot': str(slot_id), 'status': confirmation.status, 'confirmed_at': confirmation.confirmed_at})


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def display_preferences(request):
    workplace = WorkplaceSettings.load()
    preference, _ = SchedulerDisplayPreference.objects.get_or_create(
        user=request.user, defaults={'local_timezone': workplace.timezone}
    )
    if request.method == 'PATCH':
        serializer = SchedulerDisplayPreferenceSerializer(preference, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        audit(request, 'scheduler.display_preference.updated', preference)
    serializer = SchedulerDisplayPreferenceSerializer(preference)
    schedule_timezones = list(
        ScheduleMembership.objects.filter(worker__user=request.user, active=True, schedule__active=True)
        .values_list('schedule__timezone', flat=True).distinct()
    ) if request.user.role == User.Role.WORKER else []
    return Response({
        **serializer.data,
        'workplace_timezone': workplace.timezone,
        'schedule_timezones': schedule_timezones,
        'allow_overlapping_open_shifts': workplace.allow_overlapping_open_shifts,
        'require_shift_confirmation': workplace.require_shift_confirmation,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def scheduler_completion_snapshot(request):
    today = timezone.localdate()
    horizon = today + timedelta(days=31)
    annotations_view = ScheduleAnnotationViewSet()
    annotations_view.request = request
    annotations = annotations_view.get_queryset().filter(ends_on__gte=today, starts_on__lte=horizon)[:100]
    tasks_view = ScheduleTaskListViewSet()
    tasks_view.request = request
    task_lists = tasks_view.get_queryset().filter(work_date__gte=today, work_date__lte=horizon)[:100]
    preference, _ = SchedulerDisplayPreference.objects.get_or_create(user=request.user)
    pending_count = pending_confirmations_for_worker(request.user.worker_profile).count() if request.user.role == User.Role.WORKER else 0
    return Response({
        'annotations': ScheduleAnnotationSerializer(annotations, many=True, context={'request': request}).data,
        'task_lists': ScheduleTaskListSerializer(task_lists, many=True, context={'request': request}).data,
        'display': SchedulerDisplayPreferenceSerializer(preference).data,
        'pending_confirmations': pending_count,
    })
