from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, Shift, User
from .permissions import IsAdminOrManager
from .services import audit
from .shift_api import ShiftApiSerializer
from .shift_service import claim_shift, ensure_slots, refresh_shift_state, release_shift
from .shift_slots import ShiftSlot
from .workplace_access import has_capability, location_in_scope, visible_locations


class StaffingShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftApiSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'client', 'location', 'position', 'order']
    ordering_fields = ['starts_at', 'ends_at', 'created_at']
    search_fields = ['client__name', 'location__name', 'location__address', 'position__name', 'order__title', 'notes']

    def base_queryset(self):
        return Shift.objects.select_related('order','client','location','position').prefetch_related(
            'slots__worker__user', 'position__required_tag_links__tag'
        ).annotate(
            filled_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False), distinct=True),
            open_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True), distinct=True),
        ).order_by('starts_at')

    def get_queryset(self):
        user = self.request.user
        qs = self.base_queryset()
        if user.role == User.Role.ADMIN:
            return qs
        if user.role == User.Role.MANAGER:
            if not has_capability(user, 'schedule.view'):
                return qs.none()
            return qs.filter(location__in=visible_locations(user)).distinct()
        if user.role == User.Role.WORKER:
            return qs.filter(Q(slots__worker=user.worker_profile,slots__status='claimed')|Q(status=Shift.Status.PUBLISHED,slots__status='open')).distinct()
        return qs.filter(client__contacts=user).distinct()

    def get_permissions(self):
        if self.action in {'create','update','partial_update','destroy','publish','unpublish'}:
            self.required_capability = 'schedule.publish' if self.action in {'publish','unpublish'} else 'schedule.edit'
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        location = serializer.validated_data.get('location')
        if self.request.user.role == User.Role.MANAGER and (not location or not location_in_scope(self.request.user, location)):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')
        obj = serializer.save(worker=None, is_open=False)
        ensure_slots(obj)
        if obj.status == Shift.Status.PUBLISHED:
            obj.published_at = timezone.now()
            obj.save(update_fields=['published_at','updated_at'])
            refresh_shift_state(obj)
        audit(self.request,'staffing_demand.created',obj,{'required_count':obj.required_count})

    def perform_update(self, serializer):
        from .scheduling_rules import ensure_worker_eligible
        location = serializer.validated_data.get('location', serializer.instance.location)
        if self.request.user.role == User.Role.MANAGER and not location_in_scope(self.request.user, location):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Standort liegt außerhalb deines Verantwortungsbereichs.')
        with transaction.atomic():
            obj = serializer.save(worker=None)
            ensure_slots(obj)
            for slot in obj.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).select_related('worker__user'):
                ensure_worker_eligible(slot.worker, obj)
            if obj.status == Shift.Status.PUBLISHED and not obj.published_at:
                obj.published_at = timezone.now()
                obj.save(update_fields=['published_at','updated_at'])
            refresh_shift_state(obj)
            audit(self.request,'staffing_demand.updated',obj,{'required_count':obj.required_count})

    def _list_response(self, qs):
        page = self.paginate_queryset(qs)
        data = self.get_serializer(page if page is not None else qs, many=True).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    @action(detail=False, methods=['get'])
    def available(self, request):
        if request.user.role != User.Role.WORKER:
            return Response({'detail':'Nur Mitarbeiter können verfügbare Schichten abrufen.'},status=403)
        from .self_service_service import worker_can_access_open_shift
        worker = request.user.worker_profile
        base = self.filter_queryset(
            self.base_queryset().filter(
                status=Shift.Status.PUBLISHED,
                starts_at__gte=timezone.now(),
                slots__status=ShiftSlot.Status.OPEN,
            ).exclude(slots__worker=worker).distinct()
        )
        allowed_ids = []
        for shift in base:
            allowed, _ = worker_can_access_open_shift(worker, shift)
            if allowed:
                allowed_ids.append(shift.id)
        return self._list_response(self.base_queryset().filter(pk__in=allowed_ids))

    @action(detail=False, methods=['get'])
    def mine(self, request):
        if request.user.role != User.Role.WORKER:
            return Response({'detail':'Nur Mitarbeiter können eigene Schichten abrufen.'},status=403)
        qs = self.filter_queryset(self.base_queryset().filter(slots__worker=request.user.worker_profile,slots__status='claimed').distinct())
        return self._list_response(qs)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def publish(self, request, pk=None):
        shift = self.get_object(); ensure_slots(shift)
        shift.status=Shift.Status.PUBLISHED; shift.published_at=timezone.now(); shift.save(update_fields=['status','published_at','updated_at']); refresh_shift_state(shift)
        audit(request,'staffing_demand.published',shift)
        return Response(self.get_serializer(self.base_queryset().get(pk=shift.pk)).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAdminOrManager])
    def unpublish(self, request, pk=None):
        shift = self.get_object()
        if shift.slots.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False).exists():
            return Response({'detail':'Belegte Schichten können nicht zurück in den Entwurf gesetzt werden.'},status=409)
        if shift.status in {Shift.Status.CANCELLED, Shift.Status.COMPLETED}:
            return Response({'detail':'Abgeschlossene oder stornierte Schichten können nicht zurückgezogen werden.'},status=409)
        shift.status=Shift.Status.DRAFT; shift.is_open=False; shift.save(update_fields=['status','is_open','updated_at'])
        audit(request,'staffing_demand.unpublished',shift)
        return Response(self.get_serializer(self.base_queryset().get(pk=shift.pk)).data)

    @action(detail=True, methods=['post'])
    def claim(self, request, pk=None):
        if request.user.role != User.Role.WORKER:
            return Response({'detail':'Nur Mitarbeiter können eine offene Schicht übernehmen.'},status=403)
        shift = self.base_queryset().filter(pk=pk).first()
        if not shift:
            return Response({'detail':'Schicht wurde nicht gefunden.'},status=404)
        if not shift.slots.filter(status=ShiftSlot.Status.OPEN, worker__isnull=True).exists():
            return Response({'detail':'Diese Schicht ist bereits vollständig besetzt.'},status=400)

        # Backward-compatible urgent pickup: a published shift that has already
        # started but has not ended may still be claimed directly. Future shifts
        # continue through the configurable OpenShift bid/approval workflow.
        if shift.status == Shift.Status.PUBLISHED and shift.starts_at <= timezone.now() < shift.ends_at:
            try:
                slot = claim_shift(pk, request.user.worker_profile)
            except Exception as exc:
                detail=getattr(exc,'detail',str(exc)); detail=detail[0] if isinstance(detail,list) else detail
                return Response({'detail':str(detail)},status=400)
            Notification.objects.get_or_create(
                user=request.user,
                kind=f'shift-claimed-{slot.id}',
                defaults={
                    'title':'Schicht übernommen',
                    'body':f'{slot.shift.starts_at:%d.%m.%Y %H:%M} – {slot.shift.location.name}',
                    'action_url':'/schedule',
                },
            )
            audit(request,'shift.claimed',slot.shift,{'slot':str(slot.id),'late_pickup':True})
            return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)

        from .self_service_service import submit_open_shift_request
        try:
            bid, slot = submit_open_shift_request(request.user.worker_profile, shift, request.data.get('note', ''))
        except Exception as exc:
            detail=getattr(exc,'detail',str(exc)); detail=detail[0] if isinstance(detail,list) else detail
            return Response({'detail':str(detail)},status=400)
        if slot:
            Notification.objects.get_or_create(
                user=request.user,
                kind=f'shift-claimed-{slot.id}',
                defaults={
                    'title':'Schicht übernommen',
                    'body':f'{slot.shift.starts_at:%d.%m.%Y %H:%M} – {slot.shift.location.name}',
                    'action_url':'/schedule',
                },
            )
            audit(request,'shift.claimed',slot.shift,{'slot':str(slot.id),'open_shift_request':str(bid.id)})
            return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)
        audit(request,'shift.bid_created',shift,{'open_shift_request':str(bid.id)})
        return Response({
            'shift': self.get_serializer(self.base_queryset().get(pk=pk)).data,
            'request': {'id': str(bid.id), 'status': bid.status},
            'detail': 'Bewerbung wurde zur Genehmigung gesendet.',
        },status=202)

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        if request.user.role != User.Role.WORKER:
            return Response({'detail':'Nur Mitarbeiter können eine eigene Schicht freigeben.'},status=403)
        shift = self.base_queryset().filter(pk=pk).first()
        if not shift:
            return Response({'detail':'Schicht wurde nicht gefunden.'},status=404)
        from .self_service_service import validate_release
        try:
            validate_release(request.user.worker_profile, shift)
            slot=release_shift(pk,request.user.worker_profile)
        except Exception as exc:
            detail=getattr(exc,'detail',str(exc)); detail=detail[0] if isinstance(detail,list) else detail
            return Response({'detail':str(detail)},status=403 if exc.__class__.__name__ == 'PermissionDenied' else 400)
        audit(request,'shift.released_to_pool',slot.shift,{'slot':str(slot.id)})
        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)