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


class StaffingShiftViewSet(viewsets.ModelViewSet):
    queryset = Shift.objects.all()
    serializer_class = ShiftApiSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'client', 'location', 'position', 'order']
    ordering_fields = ['starts_at', 'ends_at', 'created_at']
    search_fields = ['client__name', 'location__name', 'location__address', 'position__name', 'order__title', 'notes']

    def base_queryset(self):
        return Shift.objects.select_related('order','client','location','position').annotate(
            filled_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.CLAIMED, slots__worker__isnull=False), distinct=True),
            open_count=Count('slots', filter=Q(slots__status=ShiftSlot.Status.OPEN, slots__worker__isnull=True), distinct=True),
        ).order_by('starts_at')

    def get_queryset(self):
        user = self.request.user
        qs = self.base_queryset()
        if user.role in {User.Role.ADMIN, User.Role.MANAGER}:
            return qs
        if user.role == User.Role.WORKER:
            return qs.filter(Q(slots__worker=user.worker_profile,slots__status='claimed')|Q(status=Shift.Status.PUBLISHED,slots__status='open')).distinct()
        return qs.filter(client__contacts=user).distinct()

    def get_permissions(self):
        if self.action in {'create','update','partial_update','destroy','publish','unpublish'}:
            return [IsAdminOrManager()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        obj = serializer.save(worker=None, is_open=False)
        ensure_slots(obj)
        if obj.status == Shift.Status.PUBLISHED:
            obj.published_at = timezone.now()
            obj.save(update_fields=['published_at','updated_at'])
            refresh_shift_state(obj)
        audit(self.request,'staffing_demand.created',obj,{'required_count':obj.required_count})

    def perform_update(self, serializer):
        from .scheduling_rules import ensure_worker_eligible

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
        qs = self.filter_queryset(self.base_queryset().filter(status=Shift.Status.PUBLISHED,starts_at__gte=timezone.now(),slots__status='open').exclude(slots__worker=request.user.worker_profile).distinct())
        return self._list_response(qs)

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
        try:
            slot=claim_shift(pk,request.user.worker_profile)
        except Exception as exc:
            detail=getattr(exc,'detail',str(exc)); detail=detail[0] if isinstance(detail,list) else detail
            return Response({'detail':str(detail)},status=400)
        Notification.objects.get_or_create(user=request.user,kind=f'shift-claimed-{slot.id}',defaults={'title':'Schicht übernommen','body':f'{slot.shift.starts_at:%d.%m.%Y %H:%M} – {slot.shift.location.name}','action_url':'/schedule'})
        audit(request,'shift.claimed',slot.shift,{'slot':str(slot.id)})
        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        if request.user.role != User.Role.WORKER:
            return Response({'detail':'Nur Mitarbeiter können eine eigene Schicht freigeben.'},status=403)
        try:
            slot=release_shift(pk,request.user.worker_profile)
        except Exception as exc:
            detail=getattr(exc,'detail',str(exc)); detail=detail[0] if isinstance(detail,list) else detail
            return Response({'detail':str(detail)},status=400)
        audit(request,'shift.released_to_pool',slot.shift,{'slot':str(slot.id)})
        return Response(self.get_serializer(self.base_queryset().get(pk=pk)).data)
