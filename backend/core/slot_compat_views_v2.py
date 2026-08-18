from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .advanced_views import (
    MANAGER_ROLES,
    _as_dt,
    _aware_start,
    _is_manager,
    _manager_required,
    _month_bounds,
    _readiness,
    _serialize_swap,
)
from .models import (
    Availability,
    ClientCompany,
    ClientOrder,
    Contract,
    Document,
    Notification,
    Shift,
    ShiftSwapRequest,
    TimeEntry,
    TimeOffRequest,
    User,
    WorkerProfile,
)
from .serializers import AvailabilitySerializer, NotificationSerializer, ShiftSerializer
from .services import audit
from .shift_service import ensure_worker_can_claim, refresh_shift_state
from .shift_slots import ShiftSlot


def _assignment_pairs(start=None, end=None):
    """Unique worker/shift assignments from native slots plus legacy Shift.worker."""
    slot_qs = (
        ShiftSlot.objects.filter(status=ShiftSlot.Status.CLAIMED, worker__isnull=False)
        .exclude(shift__status=Shift.Status.CANCELLED)
        .select_related(
            'worker__user',
            'shift__client',
            'shift__location',
            'shift__position',
            'shift__order',
        )
    )
    legacy_qs = (
        Shift.objects.filter(worker__isnull=False)
        .exclude(status=Shift.Status.CANCELLED)
        .select_related('worker__user', 'client', 'location', 'position', 'order')
    )
    if start is not None:
        slot_qs = slot_qs.filter(shift__ends_at__gt=start)
        legacy_qs = legacy_qs.filter(ends_at__gt=start)
    if end is not None:
        slot_qs = slot_qs.filter(shift__starts_at__lt=end)
        legacy_qs = legacy_qs.filter(starts_at__lt=end)

    pairs = []
    seen = set()
    for slot in slot_qs.order_by('worker_id', 'shift__starts_at', 'created_at'):
        key = (slot.worker_id, slot.shift_id)
        if key not in seen:
            seen.add(key)
            pairs.append((slot.worker, slot.shift))
    for shift in legacy_qs.order_by('worker_id', 'starts_at'):
        key = (shift.worker_id, shift.id)
        if key not in seen:
            seen.add(key)
            pairs.append((shift.worker, shift))
    return pairs


def _schedule_findings(date_from=None, date_to=None):
    now = timezone.now()
    start = date_from or now - timedelta(days=7)
    end = date_to or now + timedelta(days=90)
    assignments = _assignment_pairs(start, end)

    by_worker = defaultdict(list)
    for worker, shift in assignments:
        by_worker[worker.id].append((worker, shift))

    conflicts = []
    for rows in by_worker.values():
        rows.sort(key=lambda item: item[1].starts_at)
        for (worker, previous), (_, current) in zip(rows, rows[1:]):
            if current.starts_at < previous.ends_at:
                conflicts.append(
                    {
                        'worker': str(worker.id),
                        'worker_name': worker.user.get_full_name() or worker.user.email,
                        'first_shift': str(previous.id),
                        'second_shift': str(current.id),
                        'first_window': [previous.starts_at, previous.ends_at],
                        'second_window': [current.starts_at, current.ends_at],
                        'severity': 'error',
                        'message': 'Zwei Schichten überschneiden sich.',
                    }
                )

    unavailable = []
    for availability in Availability.objects.filter(
        available=False,
        starts_at__lt=end,
        ends_at__gt=start,
    ).select_related('worker__user'):
        matches = [
            shift
            for _, shift in by_worker.get(availability.worker_id, [])
            if shift.starts_at < availability.ends_at and shift.ends_at > availability.starts_at
        ]
        for shift in matches:
            unavailable.append(
                {
                    'worker': str(availability.worker_id),
                    'worker_name': availability.worker.user.get_full_name() or availability.worker.user.email,
                    'shift': str(shift.id),
                    'starts_at': shift.starts_at,
                    'ends_at': shift.ends_at,
                    'message': 'Mitarbeiter ist in diesem Zeitraum als nicht verfügbar eingetragen.',
                    'severity': 'warning',
                }
            )

    coverage = []
    orders = ClientOrder.objects.filter(
        starts_at__lt=end,
        ends_at__gt=start,
        status__in=[ClientOrder.Status.NEW, ClientOrder.Status.PLANNING, ClientOrder.Status.CONFIRMED],
    ).select_related('client', 'location')
    for order in orders:
        native_pairs = set(
            ShiftSlot.objects.filter(
                shift__order=order,
                status=ShiftSlot.Status.CLAIMED,
                worker__isnull=False,
            ).values_list('worker_id', 'shift_id')
        )
        legacy_pairs = set(
            Shift.objects.filter(order=order, worker__isnull=False)
            .exclude(status=Shift.Status.CANCELLED)
            .values_list('worker_id', 'id')
        )
        assigned = len(native_pairs | legacy_pairs)
        open_count = (
            ShiftSlot.objects.filter(
                shift__order=order,
                status=ShiftSlot.Status.OPEN,
                worker__isnull=True,
            )
            .exclude(shift__status=Shift.Status.CANCELLED)
            .count()
        )
        gap = max(0, order.requested_staff - assigned)
        if gap:
            coverage.append(
                {
                    'order': str(order.id),
                    'client': str(order.client_id),
                    'title': order.title,
                    'client_name': order.client.name,
                    'requested': order.requested_staff,
                    'assigned': assigned,
                    'open_shifts': open_count,
                    'gap': gap,
                    'starts_at': order.starts_at,
                    'severity': 'warning',
                    'message': f'{gap} Position(en) sind noch nicht fest besetzt.',
                }
            )

    month_start, month_end = _month_bounds()
    minutes_by_worker = defaultdict(int)
    for worker, shift in _assignment_pairs(_aware_start(month_start), _aware_start(month_end)):
        minutes_by_worker[worker.id] += max(
            0,
            int((shift.ends_at - shift.starts_at).total_seconds() // 60) - shift.break_minutes,
        )

    overtime = []
    for worker in WorkerProfile.objects.filter(active=True, monthly_hours__isnull=False).select_related('user'):
        minutes = minutes_by_worker.get(worker.id, 0)
        target = int(Decimal(worker.monthly_hours) * 60)
        if minutes > target:
            overtime.append(
                {
                    'worker': str(worker.id),
                    'worker_name': worker.user.get_full_name() or worker.user.email,
                    'scheduled_minutes': minutes,
                    'target_minutes': target,
                    'difference_minutes': minutes - target,
                    'severity': 'warning',
                    'message': 'Geplante Monatsstunden überschreiten das hinterlegte Stundenkonto.',
                }
            )

    return {
        'conflicts': conflicts,
        'unavailable_assignments': unavailable,
        'coverage_gaps': coverage,
        'overtime_risks': overtime,
    }


@api_view(['GET'])
def operations_overview(request):
    user = request.user
    now = timezone.now()
    notifications = Notification.objects.filter(user=user).order_by('-created_at')[:30]
    data = {
        'role': user.role,
        'notifications': NotificationSerializer(notifications, many=True).data,
        'unread_notifications': Notification.objects.filter(user=user, read_at__isnull=True).count(),
        'readiness': _readiness() if _is_manager(user) else None,
    }

    if _is_manager(user):
        findings = _schedule_findings()
        month_start, month_end = _month_bounds()
        estimated_cost = Decimal('0')
        for worker, shift in _assignment_pairs(_aware_start(month_start), _aware_start(month_end)):
            minutes = max(
                0,
                int((shift.ends_at - shift.starts_at).total_seconds() // 60) - shift.break_minutes,
            )
            rate = worker.tariff_hourly_rate or Decimal('0')
            allowance = worker.extra_allowance or Decimal('0')
            estimated_cost += (Decimal(minutes) / Decimal(60)) * (rate + allowance)
        data.update(
            {
                **findings,
                'estimated_monthly_labor_cost': str(estimated_cost.quantize(Decimal('0.01'))),
                'pending_swaps': ShiftSwapRequest.objects.filter(status=ShiftSwapRequest.Status.PENDING).count(),
                'swaps': [
                    _serialize_swap(item)
                    for item in ShiftSwapRequest.objects.select_related(
                        'shift__position', 'requested_by__user', 'offered_to__user'
                    ).order_by('-created_at')[:50]
                ],
                'swap_candidates': [
                    {'id': str(worker.id), 'name': worker.user.get_full_name() or worker.user.email}
                    for worker in WorkerProfile.objects.filter(active=True)
                    .select_related('user')
                    .order_by('user__first_name')
                ],
                'pending_time_off': TimeOffRequest.objects.filter(status=TimeOffRequest.Status.PENDING).count(),
                'unapproved_time_entries': TimeEntry.objects.filter(
                    approved=False, clock_out__isnull=False
                ).count(),
                'missing_clock_outs': TimeEntry.objects.filter(
                    clock_out__isnull=True,
                    clock_in__lt=now - timedelta(hours=16),
                ).count(),
                'contracts_due_30': Contract.objects.filter(
                    ends_on__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30)),
                    status__in=[Contract.Status.READY, Contract.Status.SENT, Contract.Status.SIGNED],
                ).count(),
                'active_workers': WorkerProfile.objects.filter(active=True).count(),
                'active_clients': ClientCompany.objects.filter(active=True).count(),
            }
        )
    elif user.role == User.Role.WORKER:
        worker = user.worker_profile
        upcoming = (
            Shift.objects.filter(
                Q(slots__worker=worker, slots__status=ShiftSlot.Status.CLAIMED) | Q(worker=worker),
                starts_at__gte=now,
            )
            .exclude(status=Shift.Status.CANCELLED)
            .distinct()
            .order_by('starts_at')[:20]
        )
        data.update(
            {
                'current_worker_id': str(worker.id),
                'swap_candidates': [
                    {'id': str(candidate.id), 'name': candidate.user.get_full_name() or candidate.user.email}
                    for candidate in WorkerProfile.objects.filter(active=True)
                    .exclude(pk=worker.pk)
                    .select_related('user')
                    .order_by('user__first_name')
                ],
                'availabilities': AvailabilitySerializer(
                    Availability.objects.filter(worker=worker).order_by('-starts_at')[:30], many=True
                ).data,
                'swaps': [
                    _serialize_swap(item)
                    for item in ShiftSwapRequest.objects.filter(
                        Q(requested_by=worker) | Q(offered_to=worker)
                    )
                    .select_related('shift__position', 'requested_by__user', 'offered_to__user')
                    .order_by('-created_at')[:30]
                ],
                'upcoming_shifts': ShiftSerializer(upcoming, many=True).data,
            }
        )
    else:
        companies = user.client_companies.all()
        company_ids = {str(pk) for pk in companies.values_list('pk', flat=True)}
        client_findings = _schedule_findings()['coverage_gaps']
        data.update(
            {
                'coverage_gaps': [item for item in client_findings if item.get('client') in company_ids],
                'contracts_due': Contract.objects.filter(
                    client__in=companies,
                    ends_on__range=(timezone.localdate(), timezone.localdate() + timedelta(days=30)),
                ).count(),
                'documents': Document.objects.filter(client__in=companies).count(),
                'open_orders': ClientOrder.objects.filter(
                    client__in=companies,
                    status__in=[
                        ClientOrder.Status.NEW,
                        ClientOrder.Status.PLANNING,
                        ClientOrder.Status.CONFIRMED,
                    ],
                ).count(),
            }
        )
    return Response(data)


@api_view(['GET'])
def schedule_quality(request):
    denied = _manager_required(request)
    if denied:
        return denied
    try:
        date_from = _as_dt(request.GET.get('date_from'), 'Von') if request.GET.get('date_from') else None
        date_to = _as_dt(request.GET.get('date_to'), 'Bis') if request.GET.get('date_to') else None
    except ValueError as exc:
        return Response({'detail': str(exc)}, status=400)
    return Response(_schedule_findings(date_from, date_to))


@api_view(['POST'])
def swap_create(request):
    if request.user.role != User.Role.WORKER:
        return Response({'detail': 'Schichttausch kann nur von Mitarbeitern angefragt werden.'}, status=403)
    try:
        shift = Shift.objects.select_related('worker__user', 'position').get(pk=request.data.get('shift'))
    except Shift.DoesNotExist:
        return Response({'detail': 'Schicht wurde nicht gefunden.'}, status=404)

    worker = request.user.worker_profile
    owns_native_slot = ShiftSlot.objects.filter(
        shift=shift,
        worker=worker,
        status=ShiftSlot.Status.CLAIMED,
    ).exists()
    if not owns_native_slot and shift.worker_id != worker.id:
        return Response({'detail': 'Du kannst nur eine eigene Schicht tauschen.'}, status=403)

    offered_to = None
    if request.data.get('offered_to'):
        try:
            offered_to = WorkerProfile.objects.get(pk=request.data.get('offered_to'), active=True)
        except WorkerProfile.DoesNotExist:
            return Response({'detail': 'Zielmitarbeiter wurde nicht gefunden.'}, status=404)
        if offered_to.id == worker.id:
            return Response({'detail': 'Eine Schicht kann nicht mit dir selbst getauscht werden.'}, status=400)

    if ShiftSwapRequest.objects.filter(
        shift=shift,
        requested_by=worker,
        status=ShiftSwapRequest.Status.PENDING,
    ).exists():
        return Response({'detail': 'Für diese Schicht besteht bereits eine offene Tauschanfrage.'}, status=400)

    obj = ShiftSwapRequest.objects.create(
        shift=shift,
        requested_by=worker,
        offered_to=offered_to,
        note=str(request.data.get('note', '')).strip(),
    )
    recipients = User.objects.filter(role__in=MANAGER_ROLES, is_active=True)
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


def _validation_detail(exc):
    detail = getattr(exc, 'detail', str(exc))
    if isinstance(detail, (list, tuple)):
        return str(detail[0]) if detail else 'Planungsregel verletzt.'
    if isinstance(detail, dict):
        first = next(iter(detail.values()), 'Planungsregel verletzt.')
        if isinstance(first, (list, tuple)):
            return str(first[0]) if first else 'Planungsregel verletzt.'
        return str(first)
    return str(detail)


@api_view(['POST'])
def swap_decide(request, pk):
    try:
        obj = ShiftSwapRequest.objects.select_related(
            'shift__worker__user',
            'shift__position',
            'requested_by__user',
            'offered_to__user',
        ).get(pk=pk)
    except ShiftSwapRequest.DoesNotExist:
        return Response({'detail': 'Tauschanfrage wurde nicht gefunden.'}, status=404)

    decision = str(request.data.get('status', '')).lower()
    user = request.user
    if _is_manager(user) and request.data.get('offered_to'):
        try:
            obj.offered_to = WorkerProfile.objects.get(pk=request.data.get('offered_to'), active=True)
            obj.save(update_fields=['offered_to'])
        except WorkerProfile.DoesNotExist:
            return Response({'detail': 'Zielmitarbeiter wurde nicht gefunden.'}, status=404)

    if decision == ShiftSwapRequest.Status.CANCELLED:
        if obj.requested_by.user_id != user.id and not _is_manager(user):
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        obj.status = ShiftSwapRequest.Status.CANCELLED
        obj.save(update_fields=['status'])
    elif decision in {ShiftSwapRequest.Status.APPROVED, ShiftSwapRequest.Status.REJECTED}:
        can_decide = _is_manager(user) or (obj.offered_to_id and obj.offered_to.user_id == user.id)
        if not can_decide:
            return Response({'detail': 'Keine Berechtigung.'}, status=403)
        if decision == ShiftSwapRequest.Status.APPROVED and not obj.offered_to_id:
            return Response({'detail': 'Für die Freigabe muss ein Zielmitarbeiter ausgewählt sein.'}, status=400)

        with transaction.atomic():
            if decision == ShiftSwapRequest.Status.APPROVED:
                if obj.offered_to_id == obj.requested_by_id:
                    return Response({'detail': 'Eine Schicht kann nicht mit dir selbst getauscht werden.'}, status=400)
                if (
                    ShiftSlot.objects.filter(
                        shift=obj.shift,
                        worker=obj.offered_to,
                        status=ShiftSlot.Status.CLAIMED,
                    ).exists()
                    or obj.shift.worker_id == obj.offered_to_id
                ):
                    return Response({'detail': 'Der Zielmitarbeiter ist dieser Schicht bereits zugeordnet.'}, status=400)
                try:
                    ensure_worker_can_claim(obj.offered_to, obj.shift)
                except ValidationError as exc:
                    return Response({'detail': _validation_detail(exc)}, status=400)

                source_slot = (
                    ShiftSlot.objects.select_for_update()
                    .filter(
                        shift=obj.shift,
                        worker=obj.requested_by,
                        status=ShiftSlot.Status.CLAIMED,
                    )
                    .order_by('created_at')
                    .first()
                )
                if source_slot is None and obj.shift.worker_id == obj.requested_by_id:
                    source_slot = (
                        ShiftSlot.objects.select_for_update()
                        .filter(
                            shift=obj.shift,
                            status=ShiftSlot.Status.OPEN,
                            worker__isnull=True,
                        )
                        .order_by('created_at')
                        .first()
                    )

                if source_slot is not None:
                    source_slot.worker = obj.offered_to
                    source_slot.status = ShiftSlot.Status.CLAIMED
                    source_slot.source = 'shift_swap'
                    source_slot.claimed_at = timezone.now()
                    source_slot.released_at = None
                    source_slot.save(
                        update_fields=[
                            'worker',
                            'status',
                            'source',
                            'claimed_at',
                            'released_at',
                            'updated_at',
                        ]
                    )
                    if obj.shift.worker_id == obj.requested_by_id:
                        obj.shift.worker = None
                        obj.shift.save(update_fields=['worker', 'updated_at'])
                    refresh_shift_state(obj.shift)
                elif obj.shift.worker_id == obj.requested_by_id:
                    obj.shift.worker = obj.offered_to
                    obj.shift.is_open = False
                    obj.shift.status = Shift.Status.CONFIRMED
                    obj.shift.save(update_fields=['worker', 'is_open', 'status', 'updated_at'])
                else:
                    return Response({'detail': 'Die ursprüngliche Schichtbelegung wurde nicht gefunden.'}, status=400)

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
    if decision == ShiftSwapRequest.Status.APPROVED and obj.offered_to_id:
        Notification.objects.create(
            user=obj.offered_to.user,
            kind=f'shift-swap-assigned-{obj.id}',
            title='Schichttausch bestätigt',
            body=f'{obj.shift.starts_at:%d.%m.%Y %H:%M} · {obj.shift.position.name}',
            action_url='/schedule',
        )
    audit(request, 'shift_swap.decided', obj, {'status': obj.status})
    return Response(_serialize_swap(obj))
