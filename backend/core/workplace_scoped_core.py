from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from . import views
from .models import Availability, Location, Position, ShiftSwapRequest, TimeOffRequest, User, WorkerProfile
from .permissions import IsAdminOrManager
from .workplace_access import has_capability, visible_locations, visible_workers, worker_in_scope


def _admin(user):
    return bool(user.role == User.Role.ADMIN or user.is_superuser)


def _require(user, capability):
    if not has_capability(user, capability):
        raise PermissionDenied('Keine Berechtigung für diese Funktion.')


class ScopedUserViewSet(views.UserViewSet):
    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if _admin(user):
            return qs
        _require(user, 'people.view')
        worker_user_ids = visible_workers(user, WorkerProfile.objects.all()).values_list('user_id', flat=True)
        return qs.filter(Q(pk=user.pk) | Q(pk__in=worker_user_ids)).distinct()


class ScopedLocationViewSet(views.LocationViewSet):
    def get_queryset(self):
        user = self.request.user
        if _admin(user):
            return self.queryset
        if user.role == User.Role.MANAGER:
            if not any(has_capability(user, cap) for cap in ('schedule.view', 'attendance.view', 'clients.view')):
                return self.queryset.none()
            return visible_locations(user, self.queryset)
        return super().get_queryset()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'clients.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        _require(self.request.user, 'clients.edit')
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        _require(self.request.user, 'clients.edit')
        if not _admin(self.request.user) and not visible_locations(self.request.user).filter(pk=serializer.instance.pk).exists():
            raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')
        return super().perform_update(serializer)

    def perform_destroy(self, instance):
        _require(self.request.user, 'clients.edit')
        if not _admin(self.request.user) and not visible_locations(self.request.user).filter(pk=instance.pk).exists():
            raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')
        instance.delete()


class ScopedPositionViewSet(views.PositionViewSet):
    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'schedule.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]


class ScopedAvailabilityViewSet(views.AvailabilityViewSet):
    def get_queryset(self):
        user = self.request.user
        if _admin(user):
            return self.queryset
        if user.role == User.Role.MANAGER:
            _require(user, 'schedule.view')
            return self.queryset.filter(worker__in=visible_workers(user)).distinct()
        return super().get_queryset()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'schedule.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]


class ScopedTimeOffViewSet(views.TimeOffViewSet):
    def get_queryset(self):
        user = self.request.user
        if _admin(user):
            return self.queryset
        if user.role == User.Role.MANAGER:
            _require(user, 'attendance.view')
            return self.queryset.filter(worker__in=visible_workers(user)).distinct()
        return super().get_queryset()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'update', 'partial_update', 'destroy', 'decide'}:
            self.required_capability = 'attendance.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        from .scheduler_completion_service import ensure_time_off_allowed
        from .self_service_models import TimeOffType
        from .self_service_service import validate_time_off_request

        user = self.request.user
        worker = serializer.validated_data.get('worker')
        if user.role == User.Role.WORKER:
            worker = user.worker_profile
        if user.role == User.Role.MANAGER:
            _require(user, 'attendance.edit')
            if not worker or not worker_in_scope(user, worker):
                raise PermissionDenied('Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.')
        if worker:
            starts_on = serializer.validated_data.get('starts_on')
            ends_on = serializer.validated_data.get('ends_on')
            default_type = TimeOffType.objects.filter(code='personal', active=True).first()
            if default_type:
                validate_time_off_request(
                    worker,
                    time_off_type=default_type,
                    starts_on=starts_on,
                    ends_on=ends_on,
                    actor=user,
                    paid=False,
                    all_day=True,
                )
            else:
                ensure_time_off_allowed(worker, starts_on, ends_on)
        return super().perform_create(serializer)


class ScopedShiftSwapViewSet(views.ShiftSwapViewSet):
    def get_queryset(self):
        user = self.request.user
        if _admin(user):
            return self.queryset
        if user.role == User.Role.MANAGER:
            _require(user, 'schedule.view')
            return self.queryset.filter(shift__location__in=visible_locations(user)).distinct()
        return super().get_queryset()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'schedule.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]


class ScopedPayrollViewSet(views.PayrollViewSet):
    def get_queryset(self):
        user = self.request.user
        if _admin(user):
            return self.queryset
        if user.role == User.Role.MANAGER:
            _require(user, 'payroll.view')
            _require(user, 'wage.view')
            return self.queryset.filter(worker__in=visible_workers(user)).distinct()
        return super().get_queryset()

    def get_permissions(self):
        if getattr(self, 'action', None) in {'create', 'update', 'partial_update', 'destroy'}:
            self.required_capability = 'payroll.review'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        if self.request.user.role == User.Role.MANAGER:
            _require(self.request.user, 'wage.view')
            worker = serializer.validated_data.get('worker')
            if not worker or not worker_in_scope(self.request.user, worker):
                raise PermissionDenied('Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.')
        return super().perform_create(serializer)
