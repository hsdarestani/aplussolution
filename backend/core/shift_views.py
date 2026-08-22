from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, Shift, User, WorkerProfile
from .permissions import IsAdminOrManager
from .premium_approval_models import ShiftPickupRequest
from .premium_services import get_policy
from .services import audit
from .shift_api import ShiftApiSerializer
from .shift_service import (
    claim_shift,
    claimed_slots,
    ensure_shift_publish_allowed,
    ensure_slots,
    ensure_worker_can_claim,
    open_slots,
    refresh_shift_state,
    release_shift,
)
from .shift_slots import ShiftSlot


SYNTHETIC_MIGRATION_EMAIL_SUFFIX = '@sync.invalid'


class StaffingShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftApiSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'client', 'location', 'position', 'order']
    ordering_fields = ['starts_at', 'ends_at', 'created_at']
    search_fields = ['client__name', 'location__name', 'location__address', 'position__name', 'order__title', 'notes']

    def base_queryset(self):
        return Shift.objects.select_related('order', 'client', 'location', 'position').annotate(
            filled_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False), distinct=True),
            open_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True), distinct=True),
        ).order_by('starts_at')

    def get_queryset(self):
        user = self.request.user
        qs = self.base_queryset()
        if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return qs
        if user.role == User.Role.WORKER:
            return qs.filter(Q(slots__worker=user.worker_profile, slots__status='claimed') | Q(status=Shift.Status.PUBLISHED, slots__status='open')).distinct()
        return qs.filter(client__contacts=user).distinct()

    def get_permissions(self):
        if self.action in {'create', 'update', 'partial_update', 'destroy', 'publish', 'assign'}:
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        with transaction.atomic():
            obj = serializer.save(worker=None, is_open=False)
            ensure_slots(obj)
            if obj.status == Shift.Status.PUBLISHED:
                ensure_shift_publish_allowed(obj)
                obj.published_at = timezone.now()
                obj.save(update_fields=['published_at', 'updated_at'])
                refresh_shift_state(obj)
            audit(self.request, 'staffing_demand.created', obj, {'required_count': obj.required_count})

    def perform_update(self, serializer):
        with transaction.atomic():
            obj = serializer.save(worker=None)
            ensure_slots(obj)
            if obj.status == Shift.Status.PUBLISHED:
                ensure_shift_publish_allowed(obj)
                if not obj.published_at:
                    obj.published_at = timezone.now()
                    obj.save(update_fields=['published_at', 'updated_at'])
            refresh_shift_state(obj)
            audit(self.request, 'staffing_demand.updated', obj, {'required_count': obj.required_count})

    def _list_response(self, qs):
        page = self.paginate_queryset(qs)
        data = self.get_serializer(page if page is not None else qs, many=True).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @action(detail=False, methods=['get'])
    def available(self, request):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können verfügbare Schichten abrufen.'}, status=403)
        qs = self.filter_queryset(self.base_queryset().filter(
            status=Shift.Status.PUBLISHED, starts_at__gte=timezone.now(), slots__status='open'
        ).exclude(slots__worker=request.user.worker_profile).distinct())
        return self._list_response(qs)

    @action(detail=False, methods=['get'])
    def mine(self, request):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können eigene Schichten abrufen.'}, status=403)
        qs = self.filter_queryset(self.base_queryset().filter(
            slots__worker=request.user.worker_profile, slots__status='claimed'
        ).distinct())
        return self._list_response(qs)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def publish(self, request, pk=None):
        shift = self.get_object()
        with transaction.atomic():
            ensure_slots(shift)
            ensure_shift_publish_allowed(shift)
            shift.status = Shift.Status.PUBLISHED
            shift.published_at = timezone.now()
            shift.save(update_fields=['status', 'published_at', 'updated_at'])
            refresh_shift_state(shift)
        audit(request, 'staffing_demand.published', shift)
        return Response(self.get_serializer(self.base_queryset().get(pk=shift.pk)).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def assign(self, request, pk=None):
        raw_workers = request.data.get('workers')
        if raw_workers is None:
            single = request.data.get('worker')
            raw_workers = [single] if single else []
        if not isinstance(raw_workers, list):
            return Response({'detail': 'workers muss eine Liste von Mitarbeiter-IDs sein.'}, status=400)

        requested_ids = []
        for worker_id in raw_workers:
            value = str(worker_id or '').strip()
            if value and value not in requested_ids:
                requested_ids.append(value)
        publish_remaining = request.data.get('publish_remaining', True) not in (False, 'false', '0', 0)

        with transaction.atomic():
            shift = Shift.objects.select_for_update().select_related('location', 'position').get(pk=pk)
            ensure_slots(shift)
            if len(requested_ids) > int(shift.required_count or 1):
                return Response({'detail': f'Es können höchstens {shift.required_count} Mitarbeiter zugewiesen werden.'}, status=400)

            workers = list(
                WorkerProfile.objects.select_related('user').filter(
                    pk__in=requested_ids,
                    active=True,
                    user__is_active=True,
                ).exclude(user__email__iendswith=SYNTHETIC_MIGRATION_EMAIL_SUFFIX)
            )
            worker_by_id = {str(worker.pk): worker for worker in workers}
            missing = [worker_id for worker_id in requested_ids if worker_id not in worker_by_id]
            if missing:
                return Response({'detail': 'Mindestens ein ausgewählter Mitarbeiter ist nicht aktiv, nur ein Migrationsdatensatz oder wurde nicht gefunden.'}, status=400)
            desired_workers = [worker_by_id[worker_id] for worker_id in requested_ids]

            current_slots = list(claimed_slots(shift).select_for_update().select_related('worker__user'))
            current_by_worker = {str(slot.worker_id): slot for slot in current_slots if slot.worker_id}

            # Validate every newly assigned worker against availability, overlap and
            # working-time rules before mutating any slot.
            try:
                for worker in desired_workers:
                    if str(worker.pk) not in current_by_worker:
                        ensure_worker_can_claim(worker, shift)
            except Exception as exc:
                detail = getattr(exc, 'detail', str(exc))
                detail = detail[0] if isinstance(detail, list) else detail
                return Response({'detail': str(detail)}, status=400)

            desired_ids = {str(worker.pk) for worker in desired_workers}
            for slot in current_slots:
                if str(slot.worker_id) not in desired_ids:
                    slot.worker = None
                    slot.status = ShiftSlot.Status.OPEN
                    slot.source = 'admin_release'
                    slot.released_at = timezone.now()
                    slot.save(update_fields=['worker', 'status', 'source', 'released_at', 'updated_at'])

            newly_assigned = []
            for worker in desired_workers:
                if str(worker.pk) in current_by_worker:
                    continue
                slot = ShiftSlot.objects.select_for_update().filter(
                    shift=shift,
                    status=ShiftSlot.Status.OPEN,
                    worker__isnull=True,
                ).order_by('created_at').first()
                if not slot:
                    return Response({'detail': 'Für diese Schicht ist kein freier Platz mehr vorhanden.'}, status=400)
                slot.worker = worker
                slot.status = ShiftSlot.Status.CLAIMED
                slot.source = 'admin_assignment'
                slot.claimed_at = timezone.now()
                slot.released_at = None
                slot.save(update_fields=['worker', 'status', 'source', 'claimed_at', 'released_at', 'updated_at'])
                newly_assigned.append((slot, worker))

            free_count = open_slots(shift).count()
            if free_count == 0:
                shift.status = Shift.Status.CONFIRMED
            elif publish_remaining:
                ensure_shift_publish_allowed(shift)
                shift.status = Shift.Status.PUBLISHED
                shift.published_at = shift.published_at or timezone.now()
            else:
                shift.status = Shift.Status.DRAFT
            shift.save(update_fields=['status', 'published_at', 'updated_at'])
            refresh_shift_state(shift)

            for slot, worker in newly_assigned:
                Notification.objects.get_or_create(
                    user=worker.user,
                    kind=f'shift-admin-assigned-{slot.id}',
                    defaults={
                        'title': 'Neue Schicht zugeteilt',
                        'body': f'{timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} – {shift.location.name}',
                        'action_url': '/schedule',
                    },
                )
            audit(request, 'shift.admin_assigned', shift, {
                'workers': requested_ids,
                'publish_remaining': publish_remaining,
            })

        return Response(self.get_serializer(self.base_queryset().get(pk=shift.pk)).data)

    @action(detail=True, methods=['post'])
    def claim(self, request, pk=None):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können eine offene Schicht übernehmen.'}, status=403)
        worker = request.user.worker_profile
        policy = get_policy()
        if policy.pickup_approval_required:
            try:
                shift = Shift.objects.select_related('location', 'position').get(pk=pk)
                if shift.status != Shift.Status.PUBLISHED:
                    return Response({'detail': 'Diese Schicht ist nicht zur Übernahme veröffentlicht.'}, status=400)
                ensure_slots(shift)
                ensure_worker_can_claim(worker, shift)
                if not shift.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).exists():
                    return Response({'detail': 'Diese Schicht ist bereits vollständig besetzt.'}, status=400)
                pickup, created = ShiftPickupRequest.objects.get_or_create(
                    shift=shift, worker=worker, status=ShiftPickupRequest.Status.PENDING
                )
                if created:
                    for admin in User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True):
                        Notification.objects.create(
                            user=admin, kind=f'pickup-request-{pickup.id}', title='Schichtübernahme prüfen',
                            body=f'{request.user.get_full_name() or request.user.email} · {timezone.localtime(shift.starts_at):%d.%m.%Y %H:%M} · {shift.location.name}',
                            action_url='/operations',
                        )
                    audit(request, 'shift.pickup_requested', shift, {'request_id': str(pickup.id)})
                return Response({'pending_approval': True, 'request_id': str(pickup.id), 'created': created}, status=202)
            except Exception as exc:
                detail = getattr(exc, 'detail', str(exc))
                detail = detail[0] if isinstance(detail, list) else detail
                return Response({'detail': str(detail)}, status=400)
        try:
            slot = claim_shift(pk, worker)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            detail = detail[0] if isinstance(detail, list) else detail
            return Response({'detail': str(detail)}, status=400)
        Notification.objects.get_or_create(
            user=request.user, kind=f'shift-claimed-{slot.id}',
            defaults={'title': 'Schicht übernommen', 'body': f'{slot.shift.starts_at:%d.%m.%Y %H:%M} – {slot.shift.location.name}', 'action_url': '/schedule'},
        )
        audit(request, 'shift.claimed', slot.shift, {'slot': str(slot.id)})
        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur Mitarbeiter können eine eigene Schicht freigeben.'}, status=403)
        try:
            slot = release_shift(pk, request.user.worker_profile)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            detail = detail[0] if isinstance(detail, list) else detail
            return Response({'detail': str(detail)}, status=400)
        audit(request, 'shift.released_to_pool', slot.shift, {'slot': str(slot.id)})
        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)
