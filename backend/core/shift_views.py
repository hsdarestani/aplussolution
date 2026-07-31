from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, Shift, ShiftAssignment, User, WorkerProfile
from .permissions import IsAdminOrManager
from .services import audit
from .shift_serializers import StaffingShiftSerializer
from .shift_service import admin_assign, claim_shift, ensure_slots, refresh_shift_state, release_shift


class StaffingShiftViewSet(viewsets.ModelViewSet):
    serializer_class = StaffingShiftSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'client', 'location', 'position', 'order']
    ordering_fields = ['starts_at', 'ends_at', 'created_at']
    search_fields = [
        'client__name', 'location__name', 'location__address', 'position__name',
        'order__title', 'notes', 'assignments__worker__user__first_name',
        'assignments__worker__user__last_name', 'assignments__worker__user__email',
    ]

    def base_queryset(self):
        return Shift.objects.select_related('order', 'client', 'location', 'position').prefetch_related(
            'assignments__worker__user'
        ).order_by('starts_at')

    def get_queryset(self):
        user = self.request.user
        qs = self.base_queryset()
        if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return qs.distinct()
        if user.role == User.Role.WORKER:
            return qs.filter(
                Q(assignments__worker=user.worker_profile, assignments__status=ShiftAssignment.Status.CLAIMED)
                | Q(status=Shift.Status.PUBLISHED, assignments__status=ShiftAssignment.Status.OPEN, assignments__worker__isnull=True)
            ).distinct()
        return qs.filter(client__contacts=user).distinct()

    def get_permissions(self):
        if self.action in {'create', 'update', 'partial_update', 'destroy', 'publish', 'assign'}:
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        obj = serializer.save(worker=None, is_open=False)
        ensure_slots(obj)
        if obj.status == Shift.Status.PUBLISHED:
            obj.published_at = timezone.now()
            obj.save(update_fields=['published_at', 'updated_at'])
            refresh_shift_state(obj)
        audit(self.request, 'staffing_demand.created', obj, {'required_count': obj.required_count})

    def perform_update(self, serializer):
        obj = serializer.save(worker=None)
        ensure_slots(obj)
        if obj.status == Shift.Status.PUBLISHED and not obj.published_at:
            obj.published_at = timezone.now()
            obj.save(update_fields=['published_at', 'updated_at'])
        refresh_shift_state(obj)
        audit(self.request, 'staffing_demand.updated', obj, {'required_count': obj.required_count})

    def _paged(self, queryset):
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=False, methods=['get'])
    def available(self, request):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können verfügbare Schichten abrufen.'}, status=403)
        qs = self.filter_queryset(self.base_queryset().filter(
            status=Shift.Status.PUBLISHED,
            starts_at__gte=timezone.now(),
            assignments__status=ShiftAssignment.Status.OPEN,
            assignments__worker__isnull=True,
        ).exclude(
            assignments__worker=request.user.worker_profile,
            assignments__status=ShiftAssignment.Status.CLAIMED,
        ).distinct())
        return self._paged(qs)

    @action(detail=False, methods=['get'])
    def mine(self, request):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können eigene Schichten abrufen.'}, status=403)
        qs = self.filter_queryset(self.base_queryset().filter(
            assignments__worker=request.user.worker_profile,
            assignments__status=ShiftAssignment.Status.CLAIMED,
        ).distinct())
        return self._paged(qs)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def publish(self, request, pk=None):
        shift = self.get_object()
        ensure_slots(shift)
        shift.status = Shift.Status.PUBLISHED
        shift.published_at = timezone.now()
        shift.save(update_fields=['status', 'published_at', 'updated_at'])
        refresh_shift_state(shift)
        audit(request, 'staffing_demand.published', shift)
        return Response(self.get_serializer(self.base_queryset().get(pk=shift.pk)).data)

    @action(detail=True, methods=['post'])
    def claim(self, request, pk=None):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können eine offene Schicht übernehmen.'}, status=403)
        try:
            assignment = claim_shift(pk, request.user.worker_profile)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            if isinstance(detail, list):
                detail = detail[0]
            return Response({'detail': str(detail)}, status=400)
        Notification.objects.get_or_create(
            user=request.user,
            kind=f'shift-claimed-{assignment.id}',
            defaults={
                'title': 'Schicht übernommen',
                'body': f'{assignment.shift.starts_at:%d.%m.%Y %H:%M} – {assignment.shift.location.name}',
                'action_url': '/schedule',
            },
        )
        audit(request, 'shift.claimed', assignment.shift, {'assignment': str(assignment.id)})
        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können eine eigene Schicht freigeben.'}, status=403)
        try:
            assignment = release_shift(pk, request.user.worker_profile)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            if isinstance(detail, list):
                detail = detail[0]
            return Response({'detail': str(detail)}, status=400)
        audit(request, 'shift.released_to_pool', assignment.shift, {'assignment': str(assignment.id)})
        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def assign(self, request, pk=None):
        worker_id = request.data.get('worker')
        if not worker_id:
            return Response({'detail': 'Mitarbeiter fehlt.'}, status=400)
        try:
            worker = WorkerProfile.objects.get(pk=worker_id, active=True)
            assignment = admin_assign(pk, worker, request.data.get('assignment'))
        except WorkerProfile.DoesNotExist:
            return Response({'detail': 'Mitarbeiter wurde nicht gefunden.'}, status=404)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            if isinstance(detail, list):
                detail = detail[0]
            return Response({'detail': str(detail)}, status=400)
        Notification.objects.create(
            user=worker.user,
            kind=f'shift-admin-override-{assignment.id}',
            title='Schicht zugeteilt',
            body=f'{assignment.shift.starts_at:%d.%m.%Y %H:%M} – {assignment.shift.location.name}',
            action_url='/schedule',
        )
        audit(request, 'shift.admin_override', assignment.shift, {'assignment': str(assignment.id)})
        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)
