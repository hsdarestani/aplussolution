from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .absence_models import CoverageOffer, ShiftAbsenceCase
from .absence_service import (
    CoverageConflict,
    cancel_case,
    coverage_candidates,
    direct_replace,
    move_case_to_open,
    report_absence,
    resolve_uncovered,
    respond_to_offer,
    send_targeted_offers,
)
from .models import Shift, User, WorkerProfile
from .services import audit
from .shift_slots import ShiftSlot


def _manager(user):
    return user.role in {User.Role.ADMIN, User.Role.MANAGER}


class CoverageOfferSerializer(serializers.ModelSerializer):
    worker_name = serializers.SerializerMethodField()
    shift = serializers.UUIDField(source='case.shift_id', read_only=True)
    shift_title = serializers.CharField(source='case.shift.position.name', read_only=True)
    shift_starts_at = serializers.DateTimeField(source='case.shift.starts_at', read_only=True)
    location_name = serializers.CharField(source='case.shift.location.name', read_only=True)

    class Meta:
        model = CoverageOffer
        fields = [
            'id', 'case', 'worker', 'worker_name', 'status', 'offered_at', 'expires_at', 'responded_at',
            'eligibility_snapshot', 'note', 'shift', 'shift_title', 'shift_starts_at', 'location_name',
        ]

    def get_worker_name(self, obj):
        return obj.worker.user.get_full_name() or obj.worker.user.email


class ShiftAbsenceCaseSerializer(serializers.ModelSerializer):
    absent_worker_name = serializers.SerializerMethodField()
    replacement_worker_name = serializers.SerializerMethodField()
    shift_title = serializers.CharField(source='shift.position.name', read_only=True)
    shift_starts_at = serializers.DateTimeField(source='shift.starts_at', read_only=True)
    shift_ends_at = serializers.DateTimeField(source='shift.ends_at', read_only=True)
    location_name = serializers.CharField(source='shift.location.name', read_only=True)
    client_name = serializers.CharField(source='shift.client.name', read_only=True)
    open_offer_count = serializers.SerializerMethodField()
    offers = CoverageOfferSerializer(many=True, read_only=True)

    class Meta:
        model = ShiftAbsenceCase
        fields = [
            'id', 'shift', 'slot', 'absent_worker', 'absent_worker_name', 'replacement_worker',
            'replacement_worker_name', 'time_off_request', 'kind', 'source', 'status', 'coverage_strategy',
            'reason_note', 'manager_note', 'short_notice', 'reported_at', 'resolved_at', 'shift_title',
            'shift_starts_at', 'shift_ends_at', 'location_name', 'client_name', 'open_offer_count', 'offers',
        ]

    def get_absent_worker_name(self, obj):
        return obj.absent_worker.user.get_full_name() or obj.absent_worker.user.email

    def get_replacement_worker_name(self, obj):
        if not obj.replacement_worker_id:
            return None
        return obj.replacement_worker.user.get_full_name() or obj.replacement_worker.user.email

    def get_open_offer_count(self, obj):
        return obj.offers.filter(status=CoverageOffer.Status.PENDING).count()


class AbsenceCaseViewSet(viewsets.ReadOnlyModelViewSet):
    # Declared for DRF router basename discovery; role scoping still happens in get_queryset().
    queryset = ShiftAbsenceCase.objects.all()
    serializer_class = ShiftAbsenceCaseSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'kind', 'short_notice', 'absent_worker', 'shift']
    ordering_fields = ['reported_at', 'shift__starts_at']

    def get_queryset(self):
        qs = ShiftAbsenceCase.objects.select_related(
            'shift__position', 'shift__location', 'shift__client', 'absent_worker__user', 'replacement_worker__user'
        ).prefetch_related('offers__worker__user')
        if _manager(self.request.user):
            return qs
        if self.request.user.role == User.Role.WORKER:
            return qs.filter(absent_worker__user=self.request.user)
        return qs.none()

    def _manager_case(self):
        if not _manager(self.request.user):
            return None, Response({'detail': 'Nur die Disposition darf Ersatzmaßnahmen steuern.'}, status=403)
        return self.get_object(), None

    @action(detail=True, methods=['get'])
    def candidates(self, request, pk=None):
        case, denied = self._manager_case()
        if denied:
            return denied
        rows = coverage_candidates(case)
        return Response({
            'case': str(case.id),
            'eligible_count': sum(1 for row in rows if row['eligible']),
            'workers': rows,
        })

    @action(detail=True, methods=['post'], url_path='move-to-open')
    def move_to_open(self, request, pk=None):
        case, denied = self._manager_case()
        if denied:
            return denied
        try:
            case = move_case_to_open(case.id, request.user)
        except (CoverageConflict, serializers.ValidationError) as exc:
            return Response({'detail': str(exc.detail if hasattr(exc, 'detail') else exc)}, status=getattr(exc, 'status_code', 400))
        audit(request, 'absence.moved_to_open', case)
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=['post'])
    def offer(self, request, pk=None):
        case, denied = self._manager_case()
        if denied:
            return denied
        worker_ids = request.data.get('workers') or None
        try:
            offers = send_targeted_offers(
                case.id,
                request.user,
                worker_ids=worker_ids,
                expires_in_hours=request.data.get('expires_in_hours', 12),
                note=request.data.get('note', ''),
            )
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
        audit(request, 'absence.targeted_offers_sent', case, {'offers': len(offers)})
        return Response(CoverageOfferSerializer(offers, many=True, context={'request': request}).data, status=201)

    @action(detail=True, methods=['post'])
    def replace(self, request, pk=None):
        case, denied = self._manager_case()
        if denied:
            return denied
        worker = WorkerProfile.objects.select_related('user').filter(pk=request.data.get('worker'), active=True).first()
        if not worker:
            return Response({'detail': 'Ersatzmitarbeiter wurde nicht gefunden.'}, status=404)
        try:
            case = direct_replace(case.id, worker, request.user)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
        audit(request, 'absence.direct_replacement', case, {'replacement_worker': str(worker.id)})
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=['post'], url_path='resolve-uncovered')
    def resolve_without_replacement(self, request, pk=None):
        case, denied = self._manager_case()
        if denied:
            return denied
        try:
            case = resolve_uncovered(case.id, request.user, request.data.get('note', ''))
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
        audit(request, 'absence.resolved_uncovered', case)
        return Response(self.get_serializer(case).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        case = self.get_object()
        try:
            case = cancel_case(case.id, request.user)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
        audit(request, 'absence.cancelled', case)
        return Response(self.get_serializer(case).data)


class CoverageOfferViewSet(viewsets.ReadOnlyModelViewSet):
    # Declared for DRF router basename discovery; role scoping still happens in get_queryset().
    queryset = CoverageOffer.objects.all()
    serializer_class = CoverageOfferSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['status', 'case', 'worker']
    ordering_fields = ['offered_at', 'expires_at']

    def get_queryset(self):
        qs = CoverageOffer.objects.select_related(
            'worker__user', 'case__shift__position', 'case__shift__location'
        )
        if _manager(self.request.user):
            return qs
        if self.request.user.role == User.Role.WORKER:
            return qs.filter(worker__user=self.request.user)
        return qs.none()

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        if request.user.role != User.Role.WORKER:
            return Response({'detail': 'Nur der angefragte Mitarbeiter kann antworten.'}, status=403)
        decision = str(request.data.get('status') or request.data.get('decision') or '').lower()
        try:
            case, offer = respond_to_offer(pk, request.user.worker_profile, decision)
        except Exception as exc:
            detail = getattr(exc, 'detail', str(exc))
            return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
        audit(request, 'coverage_offer.responded', offer, {'status': offer.status})
        # The replacement worker does not need the absent employee's identity or reason.
        return Response({
            'offer': self.get_serializer(offer).data,
            'case': {
                'id': str(case.id),
                'shift': str(case.shift_id),
                'status': case.status,
                'coverage_strategy': case.coverage_strategy,
            },
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def report_callout(request):
    shift = Shift.objects.select_related('position', 'location').filter(pk=request.data.get('shift')).first()
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    slot_id = request.data.get('slot')
    if request.user.role == User.Role.WORKER:
        worker = request.user.worker_profile
        source = ShiftAbsenceCase.Source.WORKER
    elif _manager(request.user):
        worker = None
        if request.data.get('worker'):
            worker = WorkerProfile.objects.select_related('user').filter(pk=request.data.get('worker'), active=True).first()
        elif slot_id:
            slot = ShiftSlot.objects.select_related('worker__user').filter(pk=slot_id, shift=shift, worker__isnull=False).first()
            worker = slot.worker if slot else None
        elif shift.worker_id:
            worker = shift.worker
        if not worker:
            return Response({'detail': 'Mitarbeiter oder belegter Personalplatz ist erforderlich.'}, status=400)
        source = ShiftAbsenceCase.Source.MANAGER
    else:
        return Response({'detail': 'Keine Berechtigung für Ausfallmeldungen.'}, status=403)
    try:
        case = report_absence(
            shift=shift,
            absent_worker=worker,
            reported_by=request.user,
            kind=str(request.data.get('kind') or ShiftAbsenceCase.Kind.OTHER),
            note=request.data.get('note', ''),
            source=source,
            slot_id=slot_id,
        )
    except Exception as exc:
        detail = getattr(exc, 'detail', str(exc))
        return Response({'detail': str(detail)}, status=getattr(exc, 'status_code', 400))
    audit(request, 'absence.reported', case, {'short_notice': case.short_notice})
    return Response(ShiftAbsenceCaseSerializer(case, context={'request': request}).data, status=status.HTTP_201_CREATED)
