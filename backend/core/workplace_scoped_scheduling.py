from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from . import scheduling_views
from .models import User, WorkerProfile
from .workplace_access import (
    assignment_for,
    location_in_scope,
    visible_locations,
    visible_schedule_groups,
    visible_workers,
    worker_in_scope,
)


def _admin(user):
    return bool(user.role == User.Role.ADMIN or user.is_superuser)


def _is_scoped_manager(user):
    if user.role != User.Role.MANAGER:
        return False
    assignment = assignment_for(user)
    return bool(assignment and assignment.scope_mode == 'scoped')


def _guard_worker(user, worker):
    if not _admin(user) and not worker_in_scope(user, worker):
        raise PermissionDenied('Mitarbeiter liegt außerhalb deines Verantwortungsbereichs.')


def _guard_schedule(user, schedule):
    if not _admin(user) and schedule and not visible_schedule_groups(user).filter(pk=schedule.pk).exists():
        raise PermissionDenied('Dienstplan liegt außerhalb deines Verantwortungsbereichs.')


def _guard_location(user, location):
    if not _admin(user) and location and not location_in_scope(user, location):
        raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')


class ScopedScheduleGroupViewSet(scheduling_views.ScheduleGroupViewSet):
    def get_queryset(self):
        return visible_schedule_groups(self.request.user, self.queryset)

    def _guard_payload(self, serializer):
        if not _is_scoped_manager(self.request.user):
            return
        if 'locations' in serializer.validated_data:
            locations = list(serializer.validated_data.get('locations') or [])
        elif serializer.instance:
            locations = list(serializer.instance.locations.all())
        else:
            locations = []
        if not locations:
            raise PermissionDenied('Ein bereichsgebundener Dienstplan benötigt mindestens einen zugeordneten Standort.')
        allowed = set(visible_locations(self.request.user).values_list('id', flat=True))
        if any(item.id not in allowed for item in locations):
            raise PermissionDenied('Mindestens ein Standort liegt außerhalb deines Verantwortungsbereichs.')

    def perform_create(self, serializer):
        self._guard_payload(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard_payload(serializer)
        return super().perform_update(serializer)


class ScopedScheduleMembershipViewSet(scheduling_views.ScheduleMembershipViewSet):
    def get_queryset(self):
        return self.queryset.filter(
            schedule__in=visible_schedule_groups(self.request.user),
            worker__in=visible_workers(self.request.user),
        ).distinct()

    def _guard_payload(self, serializer):
        schedule = serializer.validated_data.get('schedule', getattr(serializer.instance, 'schedule', None))
        worker = serializer.validated_data.get('worker', getattr(serializer.instance, 'worker', None))
        _guard_schedule(self.request.user, schedule)
        _guard_worker(self.request.user, worker)

    def perform_create(self, serializer):
        self._guard_payload(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard_payload(serializer)
        return super().perform_update(serializer)


class ScopedWorkerPositionQualificationViewSet(scheduling_views.WorkerPositionQualificationViewSet):
    def get_queryset(self):
        return self.queryset.filter(worker__in=visible_workers(self.request.user)).distinct()

    def _guard_payload(self, serializer):
        worker = serializer.validated_data.get('worker', getattr(serializer.instance, 'worker', None))
        _guard_worker(self.request.user, worker)

    def perform_create(self, serializer):
        self._guard_payload(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard_payload(serializer)
        return super().perform_update(serializer)


class ScopedWorkerSkillTagViewSet(scheduling_views.WorkerSkillTagViewSet):
    def get_queryset(self):
        return self.queryset.filter(worker__in=visible_workers(self.request.user)).distinct()

    def _guard_payload(self, serializer):
        worker = serializer.validated_data.get('worker', getattr(serializer.instance, 'worker', None))
        _guard_worker(self.request.user, worker)

    def perform_create(self, serializer):
        self._guard_payload(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard_payload(serializer)
        return super().perform_update(serializer)


class ScopedSchedulingPolicyViewSet(scheduling_views.SchedulingPolicyViewSet):
    def get_queryset(self):
        qs = self.queryset
        if _admin(self.request.user) or not _is_scoped_manager(self.request.user):
            return qs
        schedules = visible_schedule_groups(self.request.user)
        locations = visible_locations(self.request.user)
        return qs.filter(
            Q(schedule__in=schedules) | Q(location__in=locations) | Q(schedule__isnull=True, location__isnull=True)
        ).distinct()

    def _guard_payload(self, serializer):
        if not _is_scoped_manager(self.request.user):
            return
        schedule = serializer.validated_data.get('schedule', getattr(serializer.instance, 'schedule', None))
        location = serializer.validated_data.get('location', getattr(serializer.instance, 'location', None))
        if schedule is None and location is None:
            raise PermissionDenied('Globale Planungsregeln dürfen nur mit betriebsweitem Zugriff geändert werden.')
        _guard_schedule(self.request.user, schedule)
        _guard_location(self.request.user, location)

    def perform_create(self, serializer):
        self._guard_payload(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard_payload(serializer)
        return super().perform_update(serializer)

    def perform_destroy(self, instance):
        if _is_scoped_manager(self.request.user) and instance.schedule_id is None and instance.location_id is None:
            raise PermissionDenied('Globale Planungsregeln dürfen nicht gelöscht werden.')
        _guard_schedule(self.request.user, instance.schedule)
        _guard_location(self.request.user, instance.location)
        instance.delete()


class ScopedScheduleTemplateViewSet(scheduling_views.ScheduleTemplateViewSet):
    def get_queryset(self):
        qs = self.queryset
        if _admin(self.request.user) or not _is_scoped_manager(self.request.user):
            return qs
        schedule_ids = set(visible_schedule_groups(self.request.user).values_list('id', flat=True))
        location_ids = set(visible_locations(self.request.user).values_list('id', flat=True))
        allowed = []
        for template in qs:
            if template.schedule_id and template.schedule_id not in schedule_ids:
                continue
            item_location_ids = {item.location_id for item in template.items.all()}
            if item_location_ids and not item_location_ids.issubset(location_ids):
                continue
            if not template.schedule_id and not item_location_ids:
                continue
            allowed.append(template.id)
        return qs.filter(id__in=allowed)

    def _guard_payload(self, serializer):
        if not _is_scoped_manager(self.request.user):
            return
        schedule = serializer.validated_data.get('schedule', getattr(serializer.instance, 'schedule', None))
        _guard_schedule(self.request.user, schedule)
        if 'items' in serializer.validated_data:
            items = serializer.validated_data.get('items') or []
            locations = [item.get('location') for item in items if item.get('location')]
        elif serializer.instance:
            locations = [item.location for item in serializer.instance.items.all()]
        else:
            locations = []
        for location in locations:
            _guard_location(self.request.user, location)
        if schedule is None and not locations:
            raise PermissionDenied('Eine bereichsgebundene Vorlage benötigt einen Dienstplan oder Standort.')

    def perform_create(self, serializer):
        self._guard_payload(serializer)
        return super().perform_create(serializer)

    def perform_update(self, serializer):
        self._guard_payload(serializer)
        return super().perform_update(serializer)
