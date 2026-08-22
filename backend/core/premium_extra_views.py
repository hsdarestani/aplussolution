from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import ClientCompany, Location, Notification, Shift, User, WorkerProfile
from .permissions import IsAdminOrManager
from .premium_approval_models import ShiftPickupRequest, WorkerLocationMembership
from .premium_models import ScheduleTemplate, SchedulingPolicy
from .services import audit
from .shift_service import claim_shift, ensure_worker_can_claim


def _date(value):
    return datetime.fromisoformat(str(value)).date()


def _local_dt(day, clock, tz_name):
    return datetime.combine(day, clock, tzinfo=ZoneInfo(tz_name or 'Europe/Berlin'))


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def apply_schedule_template(request, pk):
    template = get_object_or_404(ScheduleTemplate.objects.prefetch_related('items__position').select_related('location__client'), pk=pk, active=True)
    week_start = _date(request.data.get('week_start') or timezone.localdate().isoformat())
    week_start -= timedelta(days=week_start.weekday())
    location = template.location or get_object_or_404(Location, pk=request.data.get('location_id'))
    client = location.client or get_object_or_404(ClientCompany, pk=request.data.get('client_id'))
    tz_name = location.timezone or 'Europe/Berlin'
    created = []
    with transaction.atomic():
        for item in template.items.all():
            day = week_start + timedelta(days=int(item.weekday))
            start = _local_dt(day, item.start_time, tz_name)
            end_day = day + timedelta(days=1) if item.end_time <= item.start_time else day
            end = _local_dt(end_day, item.end_time, tz_name)
            shift = Shift.objects.create(
                client=client, location=location, position=item.position,
                starts_at=start, ends_at=end, break_minutes=item.break_minutes,
                status=Shift.Status.DRAFT, is_open=False, required_count=item.required_count,
                notes=item.notes,
            )
            created.append(str(shift.id))
    audit(request, 'premium.schedule_template.applied', template, {'week_start': week_start.isoformat(), 'created': len(created)})
    return Response({'created': len(created), 'shift_ids': created, 'week_start': week_start.isoformat()}, status=201)


@api_view(['GET'])
@permission_classes([IsAdminOrManager])
def pickup_requests(request):
    qs = ShiftPickupRequest.objects.select_related('worker__user', 'shift__location', 'shift__position').filter(status=ShiftPickupRequest.Status.PENDING)
    return Response([{
        'id': str(x.id), 'shift_id': str(x.shift_id), 'worker_id': str(x.worker_id),
        'worker': x.worker.user.get_full_name() or x.worker.user.email,
        'starts_at': x.shift.starts_at.isoformat(), 'location': x.shift.location.name,
        'position': x.shift.position.name, 'status': x.status,
    } for x in qs[:500]])


@api_view(['POST'])
@permission_classes([IsAdminOrManager])
def decide_pickup_request(request, pk):
    row = get_object_or_404(ShiftPickupRequest.objects.select_related('worker__user', 'shift'), pk=pk, status=ShiftPickupRequest.Status.PENDING)
    decision = request.data.get('status')
    if decision not in {ShiftPickupRequest.Status.APPROVED, ShiftPickupRequest.Status.REJECTED}:
        return Response({'detail': 'Status muss approved oder rejected sein.'}, status=400)
    with transaction.atomic():
        if decision == ShiftPickupRequest.Status.APPROVED:
            ensure_worker_can_claim(row.worker, row.shift)
            claim_shift(row.shift_id, row.worker, bypass_approval=True)
        row.status = decision
        row.decided_by = request.user
        row.decision_note = request.data.get('note') or ''
        row.save(update_fields=['status', 'decided_by', 'decision_note', 'updated_at'])
    Notification.objects.create(
        user=row.worker.user,
        kind=f'pickup-{row.id}-{decision}',
        title='Schichtübernahme genehmigt' if decision == 'approved' else 'Schichtübernahme abgelehnt',
        body=f'{timezone.localtime(row.shift.starts_at):%d.%m.%Y %H:%M}', action_url='/schedule',
    )
    audit(request, f'premium.pickup.{decision}', row.shift, {'worker_id': str(row.worker_id), 'request_id': str(row.id)})
    return Response({'id': str(row.id), 'status': row.status})


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAdminOrManager])
def worker_location_memberships(request):
    if request.method == 'POST':
        worker = get_object_or_404(WorkerProfile, pk=request.data['worker_id'])
        location = get_object_or_404(Location, pk=request.data['location_id'])
        row, _ = WorkerLocationMembership.objects.update_or_create(
            worker=worker, location=location,
            defaults={'home': bool(request.data.get('home')), 'active': request.data.get('active', True)},
        )
        if row.home:
            WorkerLocationMembership.objects.filter(worker=worker, home=True).exclude(pk=row.pk).update(home=False)
        return Response({'id': str(row.id)}, status=201)
    if request.method == 'DELETE':
        row = get_object_or_404(WorkerLocationMembership, pk=request.data.get('id') or request.query_params.get('id'))
        row.delete()
        return Response(status=204)
    qs = WorkerLocationMembership.objects.select_related('worker__user', 'location')
    return Response([{
        'id': str(x.id), 'worker_id': str(x.worker_id), 'worker': x.worker.user.get_full_name() or x.worker.user.email,
        'location_id': str(x.location_id), 'location': x.location.name, 'home': x.home, 'active': x.active,
    } for x in qs[:1000]])


@api_view(['GET'])
def schedule_timezone(request):
    policy = SchedulingPolicy.objects.filter(active=True).first()
    target = request.query_params.get('timezone') or (policy.default_timezone if policy else 'Europe/Berlin')
    if policy and not policy.timezone_toggle_enabled and request.user.role not in {User.Role.ADMIN, User.Role.MANAGER}:
        target = policy.default_timezone
    try:
        ZoneInfo(target)
    except Exception:
        return Response({'detail': 'Ungültige Zeitzone.'}, status=400)
    start = timezone.now() - timedelta(days=7)
    end = timezone.now() + timedelta(days=60)
    qs = Shift.objects.select_related('location', 'position', 'client').filter(starts_at__gte=start, starts_at__lte=end).order_by('starts_at')
    if request.user.role == User.Role.WORKER:
        qs = qs.filter(slots__worker=request.user.worker_profile, slots__status='claimed').distinct()
    elif request.user.role == User.Role.CLIENT:
        qs = qs.filter(client__contacts=request.user).distinct()
    z = ZoneInfo(target)
    return Response({'timezone': target, 'results': [{
        'id': str(s.id), 'starts_at': s.starts_at.astimezone(z).isoformat(), 'ends_at': s.ends_at.astimezone(z).isoformat(),
        'location': s.location.name, 'position': s.position.name, 'status': s.status,
    } for s in qs[:1000]]})
