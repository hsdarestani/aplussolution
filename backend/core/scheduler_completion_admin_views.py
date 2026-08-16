import re

from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Location, Shift, User
from .permissions import IsAdminOrManager
from .scheduler_completion_models import SchedulerColorOverride, SchedulerCompletionSettings
from .services import audit
from .workplace_access import has_capability, location_in_scope, visible_locations


HEX_COLOR = re.compile(r'^#[0-9a-fA-F]{6}$')


def _admin(user):
    return bool(user.role == User.Role.ADMIN or user.is_superuser)


def _can_manage(user):
    return _admin(user) or has_capability(user, 'schedule.edit')


class SchedulerColorOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchedulerColorOverride
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_color(self, value):
        if not HEX_COLOR.fullmatch(str(value or '')):
            raise serializers.ValidationError('Farbe muss als #RRGGBB angegeben werden.')
        return value.upper()

    def validate(self, attrs):
        target_type = attrs.get('target_type', getattr(self.instance, 'target_type', None))
        target_id = attrs.get('target_id', getattr(self.instance, 'target_id', None))
        request = self.context.get('request')
        if target_type == SchedulerColorOverride.Target.SHIFT:
            obj = Shift.objects.select_related('location').filter(pk=target_id).first()
            if not obj:
                raise serializers.ValidationError({'target_id': 'Schicht wurde nicht gefunden.'})
            if request and request.user.role == User.Role.MANAGER and not location_in_scope(request.user, obj.location):
                raise serializers.ValidationError({'target_id': 'Schicht liegt außerhalb deines Verantwortungsbereichs.'})
        elif target_type == SchedulerColorOverride.Target.LOCATION:
            obj = Location.objects.filter(pk=target_id).first()
            if not obj:
                raise serializers.ValidationError({'target_id': 'Einsatzort wurde nicht gefunden.'})
            if request and request.user.role == User.Role.MANAGER and not location_in_scope(request.user, obj):
                raise serializers.ValidationError({'target_id': 'Einsatzort liegt außerhalb deines Verantwortungsbereichs.'})
        else:
            raise serializers.ValidationError({'target_type': 'Ungültiges Farbziel.'})
        return attrs


class SchedulerColorOverrideViewSet(viewsets.ModelViewSet):
    serializer_class = SchedulerColorOverrideSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = SchedulerColorOverride.objects.all()
        user = self.request.user
        if _admin(user):
            return qs
        if user.role == User.Role.MANAGER:
            if not has_capability(user, 'schedule.view'):
                return qs.none()
            locations = visible_locations(user)
            shift_ids = Shift.objects.filter(location__in=locations).values_list('id', flat=True)
            location_ids = locations.values_list('id', flat=True)
            return qs.filter(
                serializers.Q(target_type='shift', target_id__in=shift_ids)
                | serializers.Q(target_type='location', target_id__in=location_ids)
            )
        return qs.none()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        if not _can_manage(self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Keine Berechtigung für Scheduler-Farben.')
        obj = serializer.save()
        audit(self.request, 'scheduler.color.created', obj)

    def perform_update(self, serializer):
        if not _can_manage(self.request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Keine Berechtigung für Scheduler-Farben.')
        obj = serializer.save()
        audit(self.request, 'scheduler.color.updated', obj)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def scheduler_completion_settings(request):
    obj = SchedulerCompletionSettings.load()
    if request.method == 'PATCH':
        if not _can_manage(request.user):
            return Response({'detail': 'Keine Berechtigung für Scheduler-Einstellungen.'}, status=403)
        for field in ('allow_overlapping_open_shifts', 'require_shift_confirmation'):
            if field in request.data:
                setattr(obj, field, request.data[field] not in (False, 'false', '0', 0))
        obj.save(update_fields=['allow_overlapping_open_shifts', 'require_shift_confirmation', 'updated_at'])
        if not obj.require_shift_confirmation:
            from .scheduler_completion_models import ShiftConfirmation
            ShiftConfirmation.objects.all().delete()
        else:
            from .scheduler_completion_service import sync_shift_confirmations
            for shift in Shift.objects.filter(status__in=[Shift.Status.PUBLISHED, Shift.Status.CONFIRMED]):
                sync_shift_confirmations(shift)
        audit(request, 'scheduler.completion_settings.updated', obj)
    return Response({
        'allow_overlapping_open_shifts': obj.allow_overlapping_open_shifts,
        'require_shift_confirmation': obj.require_shift_confirmation,
        'can_manage': _can_manage(request.user),
    })
