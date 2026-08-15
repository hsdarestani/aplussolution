from rest_framework import serializers, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Location, User, WorkerProfile
from .permissions import IsAdminOrManager
from .scheduling_models import ScheduleGroup
from .services import audit
from .workplace_access import (
    CAPABILITIES,
    assignment_for,
    capabilities_for_user,
    has_capability,
    scope_snapshot,
    seed_system_roles,
    visible_locations,
    visible_schedule_groups,
    visible_workers,
)
from .workplace_models import AccessRole, UserAccessAssignment, WorkplaceSettings


class WorkplaceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkplaceSettings
        fields = [
            'id', 'company_name', 'timezone', 'week_starts_on', 'time_format', 'currency',
            'overtime_daily_hours', 'overtime_weekly_hours', 'overtime_mode', 'overtime_multiplier',
            'labor_sharing_enabled', 'manager_can_manage_roles', 'updated_at',
        ]
        read_only_fields = ['id', 'updated_at']

    def validate_week_starts_on(self, value):
        if value > 6:
            raise serializers.ValidationError('Der Wochenstart muss zwischen 0 und 6 liegen.')
        return value

    def validate_currency(self, value):
        value = str(value).upper().strip()
        if len(value) != 3:
            raise serializers.ValidationError('Währung muss als dreistelliger ISO-Code angegeben werden.')
        return value


class AccessRoleSerializer(serializers.ModelSerializer):
    assignment_count = serializers.SerializerMethodField()

    class Meta:
        model = AccessRole
        fields = [
            'id', 'code', 'name', 'description', 'permissions', 'wage_visibility', 'is_system',
            'active', 'assignment_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['is_system', 'assignment_count', 'created_at', 'updated_at']

    def validate_permissions(self, value):
        values = list(dict.fromkeys(value or []))
        unknown = sorted(set(values) - CAPABILITIES)
        if unknown:
            raise serializers.ValidationError(f'Unbekannte Berechtigungen: {", ".join(unknown)}')
        return values

    def get_assignment_count(self, obj):
        return obj.assignments.filter(active=True).count()


class UserAccessAssignmentSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    role_name = serializers.CharField(source='access_role.name', read_only=True)
    role_code = serializers.CharField(source='access_role.code', read_only=True)
    capabilities = serializers.SerializerMethodField()
    schedule_names = serializers.SerializerMethodField()
    location_names = serializers.SerializerMethodField()
    worker_names = serializers.SerializerMethodField()

    class Meta:
        model = UserAccessAssignment
        fields = [
            'id', 'user', 'user_name', 'access_role', 'role_name', 'role_code', 'scope_mode',
            'schedule_groups', 'schedule_names', 'locations', 'location_names', 'workers', 'worker_names',
            'can_share_labor', 'active', 'capabilities', 'created_at', 'updated_at',
        ]
        read_only_fields = ['user_name', 'role_name', 'role_code', 'capabilities', 'schedule_names', 'location_names', 'worker_names', 'created_at', 'updated_at']

    def validate_user(self, value):
        if value.role not in {User.Role.ADMIN, User.Role.MANAGER}:
            raise serializers.ValidationError('Granulare Betriebsrollen können nur Administration oder Disposition zugewiesen werden.')
        return value

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.email

    def get_capabilities(self, obj):
        return capabilities_for_user(obj.user)

    def get_schedule_names(self, obj):
        return list(obj.schedule_groups.values_list('name', flat=True))

    def get_location_names(self, obj):
        return list(obj.locations.values_list('name', flat=True))

    def get_worker_names(self, obj):
        return [item.user.get_full_name() or item.user.email for item in obj.workers.select_related('user').all()]


class CapabilityViewSetMixin:
    read_capability = 'roles.view'
    write_capability = 'roles.manage'

    def get_permissions(self):
        self.required_capability = self.write_capability if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'} else self.read_capability
        return [IsAdminOrManager()]


class AccessRoleViewSet(CapabilityViewSetMixin, viewsets.ModelViewSet):
    queryset = AccessRole.objects.all()
    serializer_class = AccessRoleSerializer
    search_fields = ['name', 'code']

    def perform_create(self, serializer):
        obj = serializer.save(is_system=False)
        audit(self.request, 'workplace.role.created', obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, 'workplace.role.updated', obj)

    def perform_destroy(self, instance):
        if instance.is_system or instance.assignments.exists():
            raise serializers.ValidationError('Systemrollen oder bereits zugewiesene Rollen können nicht gelöscht werden.')
        audit(self.request, 'workplace.role.deleted', instance)
        instance.delete()


class AccessAssignmentViewSet(CapabilityViewSetMixin, viewsets.ModelViewSet):
    queryset = UserAccessAssignment.objects.select_related('user', 'access_role').prefetch_related('schedule_groups', 'locations', 'workers__user').all()
    serializer_class = UserAccessAssignmentSerializer
    filterset_fields = ['user', 'access_role', 'scope_mode', 'active']

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, 'workplace.assignment.created', obj, {'user': str(obj.user_id), 'role': obj.access_role.code})

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, 'workplace.assignment.updated', obj, {'user': str(obj.user_id), 'role': obj.access_role.code})

    def perform_destroy(self, instance):
        if instance.user_id == self.request.user.id:
            raise serializers.ValidationError('Die eigene aktive Rollen-Zuweisung kann hier nicht gelöscht werden.')
        audit(self.request, 'workplace.assignment.deleted', instance)
        instance.delete()


@api_view(['GET', 'PATCH'])
def workplace_settings(request):
    settings = WorkplaceSettings.load()
    capability = 'workplace.manage' if request.method == 'PATCH' else 'workplace.view'
    if not has_capability(request.user, capability):
        return Response({'detail': 'Nicht berechtigt.'}, status=status.HTTP_403_FORBIDDEN)
    if request.method == 'PATCH':
        serializer = WorkplaceSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        settings = serializer.save()
        audit_payload = {
            key: str(value) if key in {'overtime_daily_hours', 'overtime_weekly_hours', 'overtime_multiplier'} else value
            for key, value in serializer.validated_data.items()
        }
        audit(request, 'workplace.settings.updated', settings, audit_payload)
    return Response(WorkplaceSettingsSerializer(settings).data)


@api_view(['GET'])
def workplace_snapshot(request):
    can_view_workplace = has_capability(request.user, 'workplace.view')
    can_view_roles = has_capability(request.user, 'roles.view')
    if not can_view_workplace and not can_view_roles:
        return Response({'detail': 'Nicht berechtigt.'}, status=status.HTTP_403_FORBIDDEN)
    seed_system_roles()
    settings = WorkplaceSettings.load()
    own_assignment = assignment_for(request.user)

    if can_view_roles:
        roles = AccessRole.objects.all()
        assignments = UserAccessAssignment.objects.select_related('user', 'access_role').prefetch_related('schedule_groups', 'locations', 'workers__user').all()
        managers = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True).order_by('first_name', 'last_name', 'email')
    else:
        roles = AccessRole.objects.filter(pk=own_assignment.access_role_id) if own_assignment else AccessRole.objects.none()
        assignments = UserAccessAssignment.objects.filter(pk=own_assignment.pk).select_related('user', 'access_role').prefetch_related('schedule_groups', 'locations', 'workers__user') if own_assignment else UserAccessAssignment.objects.none()
        managers = User.objects.filter(pk=request.user.pk)

    workers = WorkerProfile.objects.filter(active=True, user__is_active=True).select_related('user').order_by('employee_number')
    schedules = ScheduleGroup.objects.filter(active=True).order_by('name')
    locations = Location.objects.filter(active=True).order_by('name')
    if request.user.role == User.Role.MANAGER and not can_view_roles:
        workers = visible_workers(request.user, workers)
        schedules = visible_schedule_groups(request.user, schedules)
        locations = visible_locations(request.user, locations)

    return Response({
        'settings': WorkplaceSettingsSerializer(settings).data,
        'roles': AccessRoleSerializer(roles, many=True).data,
        'assignments': UserAccessAssignmentSerializer(assignments, many=True).data,
        'capability_catalog': sorted(CAPABILITIES) if can_view_roles else capabilities_for_user(request.user),
        'current_user': {
            'capabilities': capabilities_for_user(request.user),
            'scope': scope_snapshot(request.user),
        },
        'managers': [
            {'id': str(item.id), 'name': item.get_full_name() or item.email, 'email': item.email, 'role': item.role}
            for item in managers
        ],
        'workers': [
            {'id': str(item.id), 'name': item.user.get_full_name() or item.user.email, 'employee_number': item.employee_number}
            for item in workers
        ],
        'schedules': [{'id': str(item.id), 'name': item.name} for item in schedules],
        'locations': [{'id': str(item.id), 'name': item.name} for item in locations],
        'can_manage_settings': has_capability(request.user, 'workplace.manage'),
        'can_manage_roles': has_capability(request.user, 'roles.manage'),
    })
