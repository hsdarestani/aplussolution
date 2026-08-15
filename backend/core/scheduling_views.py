from datetime import date

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, Shift, ShiftSwapRequest, User, WorkerProfile
from .permissions import IsAdminOrManager
from .scheduling_models import (
    PositionSkillTag,
    ScheduleGroup,
    ScheduleMembership,
    ScheduleTemplate,
    ScheduleTemplateItem,
    SchedulingPolicy,
    SkillTag,
    WorkerPositionQualification,
    WorkerSkillTag,
)
from .scheduling_rules import (
    apply_schedule_template,
    assign_worker_to_shift,
    auto_assign_shift,
    eligible_workers_for_shift,
    ensure_worker_eligible,
    policy_for_shift,
)
from .services import audit
from .shift_service import refresh_shift_state
from .shift_slots import ShiftSlot
from .workplace_access import can_share_labor, has_capability, location_in_scope, visible_workers, worker_in_scope


class NamedSerializer(serializers.ModelSerializer):
    pass


class ScheduleGroupSerializer(serializers.ModelSerializer):
    location_names = serializers.SerializerMethodField()

    class Meta:
        model = ScheduleGroup
        fields = '__all__'

    def get_location_names(self, obj):
        return list(obj.locations.values_list('name', flat=True))


class ScheduleMembershipSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    schedule_name = serializers.CharField(source='schedule.name', read_only=True)

    class Meta:
        model = ScheduleMembership
        fields = '__all__'


class WorkerPositionQualificationSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)

    class Meta:
        model = WorkerPositionQualification
        fields = '__all__'


class SkillTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillTag
        fields = '__all__'


class WorkerSkillTagSerializer(serializers.ModelSerializer):
    worker_name = serializers.CharField(source='worker.user.get_full_name', read_only=True)
    tag_name = serializers.CharField(source='tag.name', read_only=True)

    class Meta:
        model = WorkerSkillTag
        fields = '__all__'


class PositionSkillTagSerializer(serializers.ModelSerializer):
    position_name = serializers.CharField(source='position.name', read_only=True)
    tag_name = serializers.CharField(source='tag.name', read_only=True)

    class Meta:
        model = PositionSkillTag
        fields = '__all__'


class SchedulingPolicySerializer(serializers.ModelSerializer):
    schedule_name = serializers.CharField(source='schedule.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)

    class Meta:
        model = SchedulingPolicy
        fields = '__all__'


class ScheduleTemplateItemSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.name', read_only=True)
    location_name = serializers.CharField(source='location.name', read_only=True)
    position_name = serializers.CharField(source='position.name', read_only=True)

    class Meta:
        model = ScheduleTemplateItem
        exclude = ['template']


class ScheduleTemplateSerializer(serializers.ModelSerializer):
    items = ScheduleTemplateItemSerializer(many=True, required=False)
    schedule_name = serializers.CharField(source='schedule.name', read_only=True)

    class Meta:
        model = ScheduleTemplate
        fields = '__all__'

    def create(self, validated_data):
        items = validated_data.pop('items', [])
        template = ScheduleTemplate.objects.create(**validated_data)
        for item in items:
            ScheduleTemplateItem.objects.create(template=template, **item)
        return template

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        instance = super().update(instance, validated_data)
        if items is not None:
            instance.items.all().delete()
            for item in items:
                ScheduleTemplateItem.objects.create(template=instance, **item)
        return instance


class ManagerConfigViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAdminOrManager]

    def get_permissions(self):
        self.required_capability = 'schedule.view' if getattr(self, 'action', None) in {'list', 'retrieve'} else 'schedule.edit'
        return super().get_permissions()

    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, f'scheduling.{obj.__class__.__name__.lower()}.created', obj)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, f'scheduling.{obj.__class__.__name__.lower()}.updated', obj)


class ScheduleGroupViewSet(ManagerConfigViewSet):
    queryset = ScheduleGroup.objects.prefetch_related('locations').all()
    serializer_class = ScheduleGroupSerializer
    search_fields = ['name']


class ScheduleMembershipViewSet(ManagerConfigViewSet):
    queryset = ScheduleMembership.objects.select_related('schedule', 'worker__user').all()
    serializer_class = ScheduleMembershipSerializer
    filterset_fields = ['schedule', 'worker', 'active']


class WorkerPositionQualificationViewSet(ManagerConfigViewSet):
    queryset = WorkerPositionQualification.objects.select_related('worker__user', 'position').all()
    serializer_class = WorkerPositionQualificationSerializer
    filterset_fields = ['worker', 'position', 'active', 'level']


class SkillTagViewSet(ManagerConfigViewSet):
    queryset = SkillTag.objects.all()
    serializer_class = SkillTagSerializer
    search_fields = ['name']


class WorkerSkillTagViewSet(ManagerConfigViewSet):
    queryset = WorkerSkillTag.objects.select_related('worker__user', 'tag').all()
    serializer_class = WorkerSkillTagSerializer
    filterset_fields = ['worker', 'tag', 'verified']


class PositionSkillTagViewSet(ManagerConfigViewSet):
    queryset = PositionSkillTag.objects.select_related('position', 'tag').all()
    serializer_class = PositionSkillTagSerializer
    filterset_fields = ['position', 'tag', 'required']


class SchedulingPolicyViewSet(ManagerConfigViewSet):
    queryset = SchedulingPolicy.objects.select_related('schedule', 'location', 'position').all()
    serializer_class = SchedulingPolicySerializer
    filterset_fields = ['active', 'schedule', 'location', 'position']


class ScheduleTemplateViewSet(ManagerConfigViewSet):
    queryset = ScheduleTemplate.objects.select_related('schedule').prefetch_related('items__client', 'items__location', 'items__position').all()
    serializer_class = ScheduleTemplateSerializer
    filterset_fields = ['active', 'schedule']


def _shift_scope_denied(user, shift):
    return user.role == User.Role.MANAGER and not location_in_scope(user, shift.location)


def _candidate_worker_ids(user):
    if can_share_labor(user):
        return None
    return list(visible_workers(user, WorkerProfile.objects.filter(active=True, user__is_active=True)).values_list('id', flat=True))


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def eligibility(request):
    shift_id = request.GET.get('shift')
    if not shift_id:
        return Response({'detail': 'shift ist erforderlich.'}, status=400)
    shift = Shift.objects.select_related('position', 'location', 'client').filter(pk=shift_id).first()
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    if _shift_scope_denied(request.user, shift):
        return Response({'detail': 'Diese Schicht liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
    policy = policy_for_shift(shift)
    rows = eligible_workers_for_shift(shift, worker_ids=_candidate_worker_ids(request.user))
    return Response({
        'shift': str(shift.id),
        'policy': {'id': str(policy.id) if policy.id else None, 'name': policy.name},
        'eligible_count': sum(1 for row in rows if row['eligible']),
        'labor_sharing': can_share_labor(request.user),
        'workers': rows,
    })


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def assign(request):
    shift = Shift.objects.select_related('location').filter(pk=request.data.get('shift')).first()
    worker = WorkerProfile.objects.select_related('user').filter(pk=request.data.get('worker'), active=True).first()
    if not shift or not worker:
        return Response({'detail': 'Schicht oder Mitarbeiter wurde nicht gefunden.'}, status=404)
    if _shift_scope_denied(request.user, shift):
        return Response({'detail': 'Diese Schicht liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
    if request.user.role == User.Role.MANAGER and not worker_in_scope(request.user, worker) and not can_share_labor(request.user):
        return Response({'detail': 'Dieser Mitarbeiter liegt außerhalb deines Bereichs. Labor Sharing ist nicht freigegeben.'}, status=403)
    try:
        slot = assign_worker_to_shift(shift.id, worker)
    except Exception as exc:
        detail = getattr(exc, 'detail', str(exc))
        if isinstance(detail, list):
            detail = detail[0]
        return Response({'detail': str(detail)}, status=400)
    Notification.objects.get_or_create(
        user=worker.user,
        kind=f'shift-assigned-{slot.id}',
        defaults={
            'title': 'Neue Schicht zugeteilt',
            'body': f'{shift.starts_at:%d.%m.%Y %H:%M} – {shift.location.name}',
            'action_url': '/schedule',
        },
    )
    audit(request, 'scheduling.worker_assigned', shift, {'worker': str(worker.id), 'slot': str(slot.id), 'labor_shared': not worker_in_scope(request.user, worker)})
    return Response({'shift': str(shift.id), 'worker': str(worker.id), 'slot': str(slot.id)})


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def auto_assign(request):
    shift_id = request.data.get('shift')
    if not shift_id:
        return Response({'detail': 'shift ist erforderlich.'}, status=400)
    shift = Shift.objects.select_related('location').filter(pk=shift_id).first()
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    if _shift_scope_denied(request.user, shift):
        return Response({'detail': 'Diese Schicht liegt außerhalb deines Verantwortungsbereichs.'}, status=403)
    requested = request.data.get('workers') or None
    if not can_share_labor(request.user):
        allowed = set(_candidate_worker_ids(request.user) or [])
        requested = [item for item in (requested or allowed) if item in allowed or str(item) in {str(value) for value in allowed}]
    try:
        result = auto_assign_shift(shift_id, worker_ids=requested)
    except Shift.DoesNotExist:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    except Exception as exc:
        return Response({'detail': str(getattr(exc, 'detail', exc))}, status=400)
    for row in result['assigned']:
        worker = WorkerProfile.objects.select_related('user').get(pk=row['worker'])
        Notification.objects.get_or_create(
            user=worker.user,
            kind=f'auto-assigned-{row["slot"]}',
            defaults={
                'title': 'Neue Schicht automatisch zugeteilt',
                'body': 'Die Disposition hat dich anhand der Planungsregeln eingeplant.',
                'action_url': '/schedule',
            },
        )
    audit(request, 'scheduling.auto_assigned', shift, {'assigned_count': result['assigned_count'], 'labor_sharing': can_share_labor(request.user)})
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def template_apply(request, pk):
    template = ScheduleTemplate.objects.prefetch_related('items__location').filter(pk=pk, active=True).first()
    if not template:
        return Response({'detail': 'Vorlage wurde nicht gefunden.'}, status=404)
    if request.user.role == User.Role.MANAGER and any(not location_in_scope(request.user, item.location) for item in template.items.all()):
        return Response({'detail': 'Die Vorlage enthält Standorte außerhalb deines Verantwortungsbereichs.'}, status=403)
    target = parse_date(str(request.data.get('target_week_start') or ''))
    if not target:
        return Response({'detail': 'target_week_start muss JJJJ-MM-TT sein.'}, status=400)
    result = apply_schedule_template(template, target, publish=bool(request.data.get('publish', False)))
    audit(request, 'scheduling.template_applied', template, result)
    return Response(result, status=201)


def _serialize_swap(obj):
    return {
        'id': str(obj.id),
        'shift': str(obj.shift_id),
        'shift_title': obj.shift.position.name,
        'shift_starts_at': obj.shift.starts_at,
        'requested_by': str(obj.requested_by_id),
        'requested_by_name': obj.requested_by.user.get_full_name() or obj.requested_by.user.email,
        'offered_to': str(obj.offered_to_id) if obj.offered_to_id else None,
        'offered_to_name': obj.offered_to.user.get_full_name() or obj.offered_to.user.email if obj.offered_to_id else None,
        'status': obj.status,
        'note': obj.note,
        'created_at': obj.created_at,
    }


@api_view(['POST'])
def swap_create(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Schichttausch kann nur von Mitarbeitern angefragt werden.'}, status=403)
    shift = Shift.objects.select_related('position').filter(pk=request.data.get('shift')).first()
    if not shift:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)
    worker = request.user.worker_profile
    owns = ShiftSlot.objects.filter(shift=shift, worker=worker, status=ShiftSlot.Status.CLAIMED).exists() or shift.worker_id == worker.id
    if not owns:
        return Response({'detail': 'Du kannst nur eine eigene Schicht tauschen.'}, status=403)
    offered_to = None
    if request.data.get('offered_to'):
        offered_to = WorkerProfile.objects.filter(pk=request.data.get('offered_to'), active=True).first()
        if not offered_to:
            return Response({'detail': 'Zielmitarbeiter wurde nicht gefunden.'}, status=404)
        if offered_to.id == worker.id:
            return Response({'detail': 'Eine Schicht kann nicht mit dir selbst getauscht werden.'}, status=400)
    obj = ShiftSwapRequest.objects.create(
        shift=shift,
        requested_by=worker,
        offered_to=offered_to,
        note=str(request.data.get('note', '')).strip(),
    )
    recipients = User.objects.filter(role__in=[User.Role.ADMIN, User.Role.MANAGER], is_active=True)
    if offered_to:
        recipients = recipients | User.objects.filter(pk=offered_to.user_id)
    for recipient in recipients.distinct():
        Notification.objects.create(
            user=recipient,
            kind='shift-swap',
            title='Neue Schichttauschanfrage',
            body=f'{worker.user.get_full_name() or worker.user.email}: {shift.position.name}',
            action_url='/operations',
        )
    audit(request, 'shift_swap.created', obj)
    return Response(_serialize_swap(obj), status=201)


@api_view(['POST'])
def swap_decide(request, pk):
    obj = ShiftSwapRequest.objects.select_related(
        'shift__position', 'shift__location', 'requested_by__user', 'offered_to__user'
    ).filter(pk=pk).first()
    if not obj:
        return Response({'detail': 'Tauschanfrage wurde nicht gefunden.'}, status=404)
    decision = str(request.data.get('status', '')).lower()
    is_manager = request.user.role in {User.Role.ADMIN, User.Role.MANAGER}
    if request.user.role == User.Role.MANAGER:
        if not has_capability(request.user, 'schedule.edit') or not location_in_scope(request.user, obj.shift.location):
            return Response({'detail': 'Keine Berechtigung für diese Schicht.'}, status=403)
    if is_manager and request.data.get('offered_to'):
        candidate = WorkerProfile.objects.select_related('user').filter(pk=request.data.get('offered_to'), active=True).first()
        if not candidate:
            return Response({'detail': 'Zielmitarbeiter wurde nicht gefunden.'}, status=404)
        if request.user.role == User.Role.MANAGER and not worker_in_scope(request.user, candidate) and not can_share_labor(request.user):
            return Response({'detail': 'Zielmitarbeiter liegt außerhalb deines Bereichs.'}, status=403)
        obj.offered_to = candidate
        obj.save(update_fields=['offered_to'])

    if decision == ShiftSwapRequest.Status.CANCELLED:
        if obj.requested_by.user_id != request.user.id and not is_manager:
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        obj.status = decision
        obj.save(update_fields=['status'])
    elif decision in {ShiftSwapRequest.Status.APPROVED, ShiftSwapRequest.Status.REJECTED}:
        can_decide = is_manager or (obj.offered_to_id and obj.offered_to.user_id == request.user.id)
        if not can_decide:
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        if decision == ShiftSwapRequest.Status.APPROVED and not obj.offered_to_id:
            return Response({'detail': 'Für die Freigabe muss ein Zielmitarbeiter ausgewählt sein.'}, status=400)
        with transaction.atomic():
            if decision == ShiftSwapRequest.Status.APPROVED:
                try:
                    ensure_worker_eligible(obj.offered_to, obj.shift)
                except Exception as exc:
                    detail = getattr(exc, 'detail', str(exc))
                    if isinstance(detail, list):
                        detail = detail[0]
                    return Response({'detail': str(detail)}, status=400)
                slot = ShiftSlot.objects.select_for_update().filter(
                    shift=obj.shift,
                    worker=obj.requested_by,
                    status=ShiftSlot.Status.CLAIMED,
                ).first()
                if not slot:
                    return Response({'detail': 'Aktive Schichtbelegung wurde nicht gefunden.'}, status=409)
                slot.worker = obj.offered_to
                slot.source = 'shift_swap'
                slot.claimed_at = timezone.now()
                slot.save(update_fields=['worker', 'source', 'claimed_at', 'updated_at'])
                refresh_shift_state(obj.shift)
            obj.status = decision
            obj.save(update_fields=['status'])
    else:
        return Response({'detail': 'Ungültige Entscheidung.'}, status=400)

    Notification.objects.create(
        user=obj.requested_by.user,
        kind='shift-swap-decision',
        title='Schichttausch aktualisiert',
        body=f'Status: {obj.get_status_display()}',
        action_url='/operations',
    )
    audit(request, 'shift_swap.decided', obj, {'status': obj.status})
    return Response(_serialize_swap(obj))


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def scheduler_readiness(request):
    hard_modes = {
        'qualification': SchedulingPolicy.objects.filter(active=True, qualification_mode='block').count(),
        'membership': SchedulingPolicy.objects.filter(active=True, schedule_membership_mode='block').count(),
        'tags': SchedulingPolicy.objects.filter(active=True, skill_tag_mode='block').count(),
        'rest': SchedulingPolicy.objects.filter(active=True, rest_mode='block').count(),
        'hours': SchedulingPolicy.objects.filter(active=True, hours_mode='block').count(),
        'days': SchedulingPolicy.objects.filter(active=True, days_mode='block').count(),
    }
    active_workers = visible_workers(request.user, WorkerProfile.objects.filter(active=True, user__is_active=True)).count()
    qualified_workers = visible_workers(request.user, WorkerProfile.objects.filter(active=True, position_qualifications__active=True)).distinct().count()
    return Response({
        'module': 'scheduler_rules',
        'policies': SchedulingPolicy.objects.filter(active=True).count(),
        'schedules': ScheduleGroup.objects.filter(active=True).count(),
        'templates': ScheduleTemplate.objects.filter(active=True).count(),
        'tags': SkillTag.objects.filter(active=True).count(),
        'active_workers': active_workers,
        'workers_with_position_qualification': qualified_workers,
        'qualification_coverage_percent': round((qualified_workers / active_workers) * 100, 1) if active_workers else 100,
        'hard_enforcement': hard_modes,
        'labor_sharing': can_share_labor(request.user),
        'replacement_ready': bool(active_workers == qualified_workers and hard_modes['qualification'] and hard_modes['rest'] and hard_modes['hours'] and hard_modes['days']),
    })
